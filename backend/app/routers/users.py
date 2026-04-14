from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth import current_user_id, set_user_cookie
from app.db import get_conn
from app.schemas import CreateUserRequest, UserResponse

router = APIRouter(tags=["users"])


@router.post("/users", response_model=UserResponse)
async def create_user(body: CreateUserRequest, response: Response) -> UserResponse:
    username = body.username.strip()
    if not username:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "username required")
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO app_user (username) VALUES (%s) RETURNING id",
                (username,),
            )
            row = await cur.fetchone()
        await conn.commit()
    user_id = row[0]
    set_user_cookie(response, user_id)
    return UserResponse(user_id=user_id, username=username)


@router.get("/users/me", response_model=UserResponse)
async def get_me(user_id: int = Depends(current_user_id)) -> UserResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, username FROM app_user WHERE id = %s",
                (user_id,),
            )
            row = await cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return UserResponse(user_id=row[0], username=row[1])
