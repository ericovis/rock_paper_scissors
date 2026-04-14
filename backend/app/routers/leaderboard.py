from fastapi import APIRouter

from app.db import get_conn
from app.redis_client import client as redis_client
from app.schemas import LeaderboardEntry, LeaderboardResponse

router = APIRouter(tags=["leaderboard"])

LEADERBOARD_KEY = "leaderboard:wins"
USERNAME_CACHE_KEY = "leaderboard:usernames"  # hash user_id -> username


async def record_win(user_id: int, username: str) -> None:
    r = redis_client()
    await r.zincrby(LEADERBOARD_KEY, 1, str(user_id))
    await r.hset(USERNAME_CACHE_KEY, str(user_id), username)


async def rebuild_leaderboard() -> None:
    r = redis_client()
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT r.winner_id, u.username, count(*) AS wins
                FROM round r
                JOIN app_user u ON u.id = r.winner_id
                WHERE r.winner_id IS NOT NULL
                GROUP BY r.winner_id, u.username
                """
            )
            rows = await cur.fetchall()
    pipe = r.pipeline()
    pipe.delete(LEADERBOARD_KEY)
    pipe.delete(USERNAME_CACHE_KEY)
    for user_id, username, wins in rows:
        pipe.zadd(LEADERBOARD_KEY, {str(user_id): float(wins)})
        pipe.hset(USERNAME_CACHE_KEY, str(user_id), username)
    await pipe.execute()


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(limit: int = 10) -> LeaderboardResponse:
    r = redis_client()
    raw = await r.zrevrange(LEADERBOARD_KEY, 0, limit - 1, withscores=True)
    if not raw:
        return LeaderboardResponse(entries=[])
    user_ids = [uid for uid, _ in raw]
    usernames = await r.hmget(USERNAME_CACHE_KEY, user_ids)
    entries = []
    for (uid, score), username in zip(raw, usernames):
        if username is None:
            continue
        entries.append(
            LeaderboardEntry(user_id=int(uid), username=username, wins=int(score))
        )
    return LeaderboardResponse(entries=entries)
