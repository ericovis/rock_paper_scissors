import asyncio
import logging
import time
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

from app.db import get_conn
from app.redis_client import client as redis_client
from app.routers.leaderboard import record_win
from app.services.game_logic import Choice, resolve_round

log = logging.getLogger(__name__)

ROUND_TIMEOUT_S = 45
RECONNECT_GRACE_S = 10


@dataclass
class PlayerSlot:
    user_id: int
    username: str
    ws: WebSocket | None = None
    grace_task: asyncio.Task | None = None


@dataclass
class RoomSession:
    room_id: int
    p1: PlayerSlot
    p2: PlayerSlot | None = None
    round_number: int = 0
    score_p1: int = 0
    score_p2: int = 0
    p1_choice: Choice | None = None
    p2_choice: Choice | None = None
    deadline_ms: int = 0
    timeout_task: asyncio.Task | None = None
    ended: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_sessions: dict[int, RoomSession] = {}
_sessions_lock = asyncio.Lock()


# --------- Redis RoomState helpers ---------

def _room_key(room_id: int) -> str:
    return f"room:{room_id}"


async def _save_room_state(session: RoomSession) -> None:
    r = redis_client()
    await r.hset(
        _room_key(session.room_id),
        mapping={
            "round_number": session.round_number,
            "deadline_ms": session.deadline_ms,
            "p1_choice": session.p1_choice or "",
            "p2_choice": session.p2_choice or "",
            "score_p1": session.score_p1,
            "score_p2": session.score_p2,
        },
    )


async def _clear_room_state(room_id: int) -> None:
    await redis_client().delete(_room_key(room_id))


# --------- Messaging helpers ---------

async def _send(ws: WebSocket | None, event: str, data: dict | None = None) -> None:
    if ws is None:
        return
    try:
        await ws.send_json({"event": event, "data": data or {}})
    except Exception as e:
        log.warning("send failed: %s", e)


async def _broadcast(session: RoomSession, event: str, data: dict | None = None) -> None:
    await _send(session.p1.ws, event, data)
    if session.p2:
        await _send(session.p2.ws, event, data)


async def _send_error(ws: WebSocket, code: str, message: str) -> None:
    try:
        await ws.send_json({"event": "error", "data": {"code": code, "message": message}})
    except Exception:
        pass


# --------- DB helpers ---------

async def _fetch_username(user_id: int) -> str | None:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT username FROM app_user WHERE id = %s", (user_id,))
            row = await cur.fetchone()
    return row[0] if row else None


async def _claim_player_2(room_id: int, user_id: int) -> tuple[str, int | None, int | None]:
    """Returns ("ok", p1_id, p2_id) or ("error", code, None)."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT player_1_id, player_2_id, ended_at FROM game_room WHERE id = %s",
                (room_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return ("error", None, None)
            p1_id, p2_id, ended_at = row
            if ended_at is not None:
                return ("ended", None, None)
            if p1_id == user_id or p2_id == user_id:
                return ("ok", p1_id, p2_id)
            if p2_id is None:
                await cur.execute(
                    """
                    UPDATE game_room SET player_2_id = %s
                    WHERE id = %s AND player_2_id IS NULL AND ended_at IS NULL
                    RETURNING player_1_id
                    """,
                    (user_id, room_id),
                )
                updated = await cur.fetchone()
                if updated is None:
                    return ("full", None, None)
                await conn.commit()
                return ("ok", p1_id, user_id)
            return ("full", None, None)


async def _persist_round(
    room_id: int,
    round_number: int,
    p1_choice: Choice | None,
    p2_choice: Choice | None,
    winner_user_id: int | None,
) -> None:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO round
                    (game_room_id, round_number, player_1_choice, player_2_choice, winner_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (game_room_id, round_number) DO NOTHING
                """,
                (room_id, round_number, p1_choice, p2_choice, winner_user_id),
            )
        await conn.commit()


async def _mark_room_ended(room_id: int) -> None:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE game_room SET ended_at = now() WHERE id = %s AND ended_at IS NULL",
                (room_id,),
            )
        await conn.commit()


# --------- Session lifecycle ---------

async def _get_or_create_session(room_id: int, user_id: int, ws: WebSocket) -> RoomSession | str:
    """Create or fetch a session; returns error-code string on failure."""
    status, p1_id, p2_id = await _claim_player_2(room_id, user_id)
    if status == "error":
        return "room_not_found"
    if status == "ended":
        return "room_ended"
    if status == "full":
        return "room_full"
    assert p1_id is not None
    username = await _fetch_username(user_id)
    if username is None:
        return "user_not_found"

    async with _sessions_lock:
        session = _sessions.get(room_id)
        if session is None:
            p1_username = username if user_id == p1_id else (await _fetch_username(p1_id) or "?")
            session = RoomSession(
                room_id=room_id,
                p1=PlayerSlot(user_id=p1_id, username=p1_username),
            )
            _sessions[room_id] = session

    # Attach player to the correct slot.
    async with session.lock:
        if session.ended:
            return "room_ended"
        reconnected_mid_game = False
        if user_id == session.p1.user_id:
            if session.p1.ws is not None:
                return "already_connected"
            session.p1.ws = ws
            if session.p1.grace_task and not session.p1.grace_task.done():
                session.p1.grace_task.cancel()
                session.p1.grace_task = None
                await _send(session.p2.ws if session.p2 else None, "opponent_reconnected")
                reconnected_mid_game = session.round_number > 0
        else:
            if session.p2 is None:
                session.p2 = PlayerSlot(user_id=user_id, username=username, ws=ws)
            else:
                if session.p2.user_id != user_id:
                    return "room_full"
                if session.p2.ws is not None:
                    return "already_connected"
                session.p2.ws = ws
                if session.p2.grace_task and not session.p2.grace_task.done():
                    session.p2.grace_task.cancel()
                    session.p2.grace_task = None
                    await _send(session.p1.ws, "opponent_reconnected")
                    reconnected_mid_game = session.round_number > 0

        # Kick off the game if both players are now present and no round has started.
        if session.p2 and session.p1.ws and session.p2.ws and session.round_number == 0:
            await _send(session.p1.ws, "room_ready", {"opponent_username": session.p2.username})
            await _send(session.p2.ws, "room_ready", {"opponent_username": session.p1.username})
            await _start_round(session)
        elif reconnected_mid_game:
            # Re-send current round info so the reconnected client can resume the countdown.
            is_p1 = user_id == session.p1.user_id
            opponent_username = (
                session.p2.username if is_p1 and session.p2 else session.p1.username
            )
            await _send(ws, "room_ready", {"opponent_username": opponent_username})
            await _send(
                ws,
                "round_start",
                {"round_number": session.round_number, "deadline_unix_ms": session.deadline_ms},
            )

    return session


async def _start_round(session: RoomSession) -> None:
    session.round_number += 1
    session.p1_choice = None
    session.p2_choice = None
    session.deadline_ms = int(time.time() * 1000) + ROUND_TIMEOUT_S * 1000
    await _save_room_state(session)
    payload = {"round_number": session.round_number, "deadline_unix_ms": session.deadline_ms}
    await _broadcast(session, "round_start", payload)
    if session.timeout_task and not session.timeout_task.done():
        session.timeout_task.cancel()
    session.timeout_task = asyncio.create_task(_round_timeout_watcher(session))


async def _round_timeout_watcher(session: RoomSession) -> None:
    try:
        await asyncio.sleep(ROUND_TIMEOUT_S)
    except asyncio.CancelledError:
        return
    async with session.lock:
        if session.ended:
            return
        if session.p1_choice is not None and session.p2_choice is not None:
            return
        await _resolve_current_round(session)


async def _resolve_current_round(session: RoomSession) -> None:
    winner = resolve_round(session.p1_choice, session.p2_choice)
    winner_user_id: int | None = None
    if winner == "p1":
        session.score_p1 += 1
        winner_user_id = session.p1.user_id
    elif winner == "p2":
        session.score_p2 += 1
        winner_user_id = session.p2.user_id if session.p2 else None

    await _persist_round(
        session.room_id,
        session.round_number,
        session.p1_choice,
        session.p2_choice,
        winner_user_id,
    )
    if winner == "p1":
        await record_win(session.p1.user_id, session.p1.username)
    elif winner == "p2" and session.p2:
        await record_win(session.p2.user_id, session.p2.username)

    p1_payload = {
        "round_number": session.round_number,
        "your_choice": session.p1_choice,
        "opponent_choice": session.p2_choice,
        "winner": "you" if winner == "p1" else ("opponent" if winner == "p2" else "draw"),
        "score": {"you": session.score_p1, "opponent": session.score_p2},
    }
    p2_payload = {
        "round_number": session.round_number,
        "your_choice": session.p2_choice,
        "opponent_choice": session.p1_choice,
        "winner": "you" if winner == "p2" else ("opponent" if winner == "p1" else "draw"),
        "score": {"you": session.score_p2, "opponent": session.score_p1},
    }
    await _send(session.p1.ws, "round_result", p1_payload)
    if session.p2:
        await _send(session.p2.ws, "round_result", p2_payload)

    if session.timeout_task and not session.timeout_task.done():
        session.timeout_task.cancel()
    session.timeout_task = None

    if not session.ended and session.p2 and session.p1.ws and session.p2.ws:
        await _start_round(session)


# --------- Public entry point ---------

async def serve(ws: WebSocket, room_id: int, user_id: int) -> None:
    await ws.accept()
    result = await _get_or_create_session(room_id, user_id, ws)
    if isinstance(result, str):
        await _send_error(ws, result, result)
        await ws.close()
        return
    session = result

    try:
        while True:
            raw = await ws.receive_json()
            event = raw.get("event")
            data = raw.get("data") or {}
            if event == "submit_choice":
                await _handle_submit(session, user_id, data)
            elif event == "leave_room":
                await _handle_leave(session, user_id)
                break
            else:
                await _send_error(ws, "unknown_event", f"unknown event: {event}")
    except WebSocketDisconnect:
        await _handle_disconnect(session, user_id)
    except Exception as e:
        log.exception("ws error: %s", e)
        await _handle_disconnect(session, user_id)


async def _handle_submit(session: RoomSession, user_id: int, data: dict) -> None:
    choice = data.get("choice")
    if choice not in ("rock", "paper", "scissors"):
        return
    async with session.lock:
        if session.ended or session.p2 is None:
            return
        if user_id == session.p1.user_id:
            if session.p1_choice is not None:
                return
            session.p1_choice = choice
            await _send(session.p2.ws, "opponent_submitted")
        elif user_id == session.p2.user_id:
            if session.p2_choice is not None:
                return
            session.p2_choice = choice
            await _send(session.p1.ws, "opponent_submitted")
        else:
            return
        await _save_room_state(session)
        if session.p1_choice is not None and session.p2_choice is not None:
            await _resolve_current_round(session)


async def _handle_leave(session: RoomSession, user_id: int) -> None:
    async with session.lock:
        if session.ended:
            return
        session.ended = True
        if session.timeout_task and not session.timeout_task.done():
            session.timeout_task.cancel()
        other_ws = None
        if user_id == session.p1.user_id and session.p2:
            other_ws = session.p2.ws
        elif session.p2 and user_id == session.p2.user_id:
            other_ws = session.p1.ws
        await _send(other_ws, "opponent_left")
    await _mark_room_ended(session.room_id)
    await _clear_room_state(session.room_id)
    async with _sessions_lock:
        _sessions.pop(session.room_id, None)


async def _handle_disconnect(session: RoomSession, user_id: int) -> None:
    async with session.lock:
        if session.ended:
            return
        slot: PlayerSlot | None = None
        other: PlayerSlot | None = None
        if user_id == session.p1.user_id:
            slot = session.p1
            other = session.p2
        elif session.p2 and user_id == session.p2.user_id:
            slot = session.p2
            other = session.p1
        if slot is None:
            return
        slot.ws = None
        # If the opponent never joined, end the session immediately.
        if other is None:
            session.ended = True
            if session.timeout_task and not session.timeout_task.done():
                session.timeout_task.cancel()
            await _mark_room_ended(session.room_id)
            await _clear_room_state(session.room_id)
            async with _sessions_lock:
                _sessions.pop(session.room_id, None)
            return
        await _send(other.ws, "opponent_disconnected", {"grace_seconds": RECONNECT_GRACE_S})
        if slot.grace_task and not slot.grace_task.done():
            slot.grace_task.cancel()
        slot.grace_task = asyncio.create_task(_grace_watcher(session, slot))


async def _grace_watcher(session: RoomSession, slot: PlayerSlot) -> None:
    try:
        await asyncio.sleep(RECONNECT_GRACE_S)
    except asyncio.CancelledError:
        return
    async with session.lock:
        if session.ended:
            return
        if slot.ws is not None:
            return  # reconnected
        session.ended = True
        if session.timeout_task and not session.timeout_task.done():
            session.timeout_task.cancel()
        other = session.p2 if slot is session.p1 else session.p1
        await _send(other.ws, "opponent_left")
    await _mark_room_ended(session.room_id)
    await _clear_room_state(session.room_id)
    async with _sessions_lock:
        _sessions.pop(session.room_id, None)
