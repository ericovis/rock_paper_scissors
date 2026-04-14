import os
from contextlib import asynccontextmanager
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://rps:rps@postgres:5432/rps")

_pool: AsyncConnectionPool | None = None


async def init_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(DATABASE_URL, min_size=1, max_size=10, open=False)
        await _pool.open()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised")
    return _pool


@asynccontextmanager
async def get_conn():
    async with pool().connection() as conn:
        yield conn


async def bootstrap_schema() -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text()
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql)
        await conn.commit()
