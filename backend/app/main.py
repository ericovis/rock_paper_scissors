import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import bootstrap_schema, close_pool, init_pool
from app.redis_client import close_redis, init_redis
from app.routers import game, leaderboard, rooms, users
from app.routers.leaderboard import rebuild_leaderboard

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    await bootstrap_schema()
    await init_redis()
    await rebuild_leaderboard()
    try:
        yield
    finally:
        await close_redis()
        await close_pool()


app = FastAPI(title="Rock Paper Scissors", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/api")
app.include_router(rooms.router, prefix="/api")
app.include_router(leaderboard.router, prefix="/api")
app.include_router(game.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
