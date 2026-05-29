import asyncio
import pytest
import asyncpg
from core.db import get_pool, close_pool

@pytest.mark.asyncio
async def test_db_connection():
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT COUNT(*) FROM market_ticks")
        assert result == 0  # empty but exists
    await close_pool()
    print("✓ DB connection works")