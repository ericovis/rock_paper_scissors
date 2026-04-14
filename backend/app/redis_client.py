import os

import redis.asyncio as redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

_client: redis.Redis | None = None


async def init_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
        await _client.ping()
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def client() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis client not initialised")
    return _client
