from fastapi import APIRouter, WebSocket

from app.auth import COOKIE_NAME
from app.services.room_manager import serve

router = APIRouter()


@router.websocket("/ws/game/{room_id}")
async def game_ws(websocket: WebSocket, room_id: int) -> None:
    raw_user_id = websocket.cookies.get(COOKIE_NAME)
    if not raw_user_id:
        await websocket.accept()
        await websocket.send_json(
            {"event": "error", "data": {"code": "unauthenticated", "message": "missing cookie"}}
        )
        await websocket.close()
        return
    try:
        user_id = int(raw_user_id)
    except ValueError:
        await websocket.accept()
        await websocket.send_json(
            {"event": "error", "data": {"code": "unauthenticated", "message": "invalid cookie"}}
        )
        await websocket.close()
        return
    await serve(websocket, room_id, user_id)
