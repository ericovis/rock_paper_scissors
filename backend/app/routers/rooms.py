import os

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import current_user_id
from app.db import get_conn
from app.schemas import CreateRoomResponse, OpenRoom, RoomDetails

router = APIRouter(tags=["rooms"])

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")


@router.post("/rooms", response_model=CreateRoomResponse)
async def create_room(user_id: int = Depends(current_user_id)) -> CreateRoomResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id FROM app_user WHERE id = %s", (user_id,)
            )
            if await cur.fetchone() is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
            await cur.execute(
                "INSERT INTO game_room (player_1_id) VALUES (%s) RETURNING id",
                (user_id,),
            )
            row = await cur.fetchone()
        await conn.commit()
    room_id = row[0]
    return CreateRoomResponse(
        room_id=room_id,
        share_url=f"{FRONTEND_ORIGIN}/?room={room_id}",
    )


@router.get("/rooms", response_model=list[OpenRoom])
async def list_open_rooms() -> list[OpenRoom]:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT r.id, u.username, r.created_at
                FROM game_room r
                JOIN app_user u ON u.id = r.player_1_id
                WHERE r.player_2_id IS NULL AND r.ended_at IS NULL
                ORDER BY r.created_at DESC
                LIMIT 100
                """
            )
            rows = await cur.fetchall()
    return [
        OpenRoom(room_id=row[0], creator_username=row[1], created_at=row[2])
        for row in rows
    ]


@router.get("/rooms/{room_id}", response_model=RoomDetails)
async def get_room(room_id: int) -> RoomDetails:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    r.id,
                    u1.username,
                    u2.username,
                    r.created_at,
                    r.ended_at
                FROM game_room r
                JOIN app_user u1 ON u1.id = r.player_1_id
                LEFT JOIN app_user u2 ON u2.id = r.player_2_id
                WHERE r.id = %s
                """,
                (room_id,),
            )
            row = await cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "room not found")
    return RoomDetails(
        room_id=row[0],
        player_1_username=row[1],
        player_2_username=row[2],
        created_at=row[3],
        ended_at=row[4],
    )
