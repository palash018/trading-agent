import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agents.data.ingestion import write_tick, build_ws_url
from core.db import get_pool, close_pool

def test_build_ws_url():
    url = build_ws_url(["btcusdt", "ethusdt"])
    assert "btcusdt@kline_1m" in url
    assert "ethusdt@kline_1m" in url

@pytest.mark.asyncio
async def test_write_tick():
    pool = await get_pool()
    fake_kline = {
        "t": 1700000000000,
        "o": "40000.1", "h": "40100.0",
        "l": "39900.0", "c": "40050.5",
        "v": "12.345"
    }
    await write_tick(pool, "BTCUSDT", fake_kline)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM market_ticks WHERE symbol = 'BTCUSDT' ORDER BY time DESC LIMIT 1"
        )
        assert row is not None
        assert float(row["close"]) == 40050.5
        print(f"✓ Tick written: {dict(row)}")

    await close_pool()