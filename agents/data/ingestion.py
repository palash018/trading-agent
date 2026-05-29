import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import websockets
from core.db import get_pool

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("data-agent")

SYMBOLS = ["btcusdt", "ethusdt"]
WS_BASE = "wss://stream.binance.com:9443/stream"

def build_ws_url(symbols: list[str]) -> str:
    streams = "/".join(f"{s}@kline_1m" for s in symbols)
    return f"{WS_BASE}?streams={streams}"

async def write_tick(pool, symbol: str, kline: dict):
    await pool.execute("""
        INSERT INTO market_ticks (time, symbol, open, high, low, close, volume)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """,
        datetime.fromtimestamp(kline["t"] / 1000, tz=timezone.utc),
        symbol.upper(),
        float(kline["o"]),
        float(kline["h"]),
        float(kline["l"]),
        float(kline["c"]),
        float(kline["v"]),
    )

async def log_event(pool, event_type: str, message: str, metadata: dict = {}):
    await pool.execute("""
        INSERT INTO agent_events (time, agent, event_type, message, metadata)
        VALUES (NOW(), 'data-agent', $1, $2, $3)
    """, event_type, message, json.dumps(metadata))

async def run(reconnect_delay: int = 5):
    pool = await get_pool()
    url = build_ws_url(SYMBOLS)
    ticks_received = 0

    while True:
        try:
            logger.info(f"Connecting to Binance WS for {SYMBOLS}...")
            await log_event(pool, "CONNECT", f"Connecting for symbols {SYMBOLS}")

            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                logger.info("Connected.")
                await log_event(pool, "CONNECTED", "WebSocket connected successfully")

                async for raw in ws:
                    msg = json.loads(raw)
                    kline = msg["data"]["k"]
                    symbol = msg["data"]["s"]

                    # Only write on closed candles to avoid duplicates
                    if kline["x"]:
                        await write_tick(pool, symbol, kline)
                        ticks_received += 1
                        logger.info(f"[{symbol}] close={kline['c']} vol={kline['v']} | total={ticks_received}")

        except websockets.ConnectionClosed as e:
            logger.warning(f"WS closed: {e}. Reconnecting in {reconnect_delay}s...")
            await log_event(pool, "DISCONNECTED", str(e))
            await asyncio.sleep(reconnect_delay)

        except Exception as e:
            logger.error(f"Unexpected error: {e}. Reconnecting in {reconnect_delay}s...")
            await log_event(pool, "ERROR", str(e))
            await asyncio.sleep(reconnect_delay)

if __name__ == "__main__":
    asyncio.run(run())