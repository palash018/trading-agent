import asyncio
import httpx
from datetime import datetime, timezone
from core.db import get_pool, close_pool

SYMBOLS = ["BTCUSDT", "ETHUSDT"]

async def fetch_klines(symbol: str, limit: int = 100) -> list:
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": "1m", "limit": limit}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params, timeout=10)
        return r.json()

async def seed(symbol: str, pool):
    klines = await fetch_klines(symbol)
    inserted = 0
    for k in klines:
        await pool.execute("""
            INSERT INTO market_ticks (time, symbol, open, high, low, close, volume)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT DO NOTHING
        """,
            datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
            symbol,
            float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]),
        )
        inserted += 1
    print(f"[{symbol}] inserted {inserted} candles")

async def main():
    pool = await get_pool()
    for symbol in SYMBOLS:
        await seed(symbol, pool)
    await close_pool()

asyncio.run(main())
