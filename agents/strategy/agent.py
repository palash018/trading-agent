import asyncio
import json
import logging
import anthropic
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from core.db import get_pool

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("strategy-agent")

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYMBOLS = ["BTCUSDT", "ETHUSDT"]

# --- Indicators ---

def compute_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def compute_vwap(rows: list[dict]) -> float | None:
    if not rows:
        return None
    total_vol = sum(r["volume"] for r in rows)
    if total_vol == 0:
        return None
    return sum(((r["high"] + r["low"] + r["close"]) / 3) * r["volume"] for r in rows) / total_vol

# --- Data fetchers ---

async def fetch_ticks(pool, symbol: str, limit: int = 30) -> list[dict]:
    rows = await pool.fetch("""
        SELECT time, open, high, low, close, volume
        FROM market_ticks
        WHERE symbol = $1
        ORDER BY time DESC
        LIMIT $2
    """, symbol, limit)
    return [dict(r) for r in reversed(rows)]

async def fetch_sentiment(pool, symbol: str) -> dict:
    # Average sentiment score over last hour, split by source
    rows = await pool.fetch("""
        SELECT score, source, llm_used
        FROM sentiment_scores
        WHERE symbol = $1
          AND time > NOW() - INTERVAL '1 hour'
        ORDER BY time DESC
    """, symbol.replace("USDT", ""))

    if not rows:
        return {"avg": 0.0, "count": 0, "label": "neutral"}

    scores = [r["score"] for r in rows]
    avg = round(sum(scores) / len(scores), 3)
    label = "bullish" if avg > 0.2 else "bearish" if avg < -0.2 else "neutral"
    return {"avg": avg, "count": len(scores), "label": label}

# --- Claude Sonnet strategy call ---

async def generate_proposal(symbol: str, ticks: list[dict], sentiment: dict, rsi: float | None, vwap: float | None) -> dict:
    current_price = ticks[-1]["close"]
    price_change_pct = round(((ticks[-1]["close"] - ticks[0]["close"]) / ticks[0]["close"]) * 100, 2)

    context = f"""
You are a quantitative trading strategy agent. Analyze the following market data and generate a trade proposal.

Symbol: {symbol}
Current Price: {current_price}
Price Change (last {len(ticks)} candles): {price_change_pct}%
RSI (14): {rsi if rsi else 'insufficient data'}
VWAP: {round(vwap, 2) if vwap else 'N/A'}
Price vs VWAP: {'above' if vwap and current_price > vwap else 'below'}

Sentiment (last 1hr):
  - Average score: {sentiment['avg']} ({sentiment['label']})
  - Based on {sentiment['count']} articles

Recent closes (oldest → newest):
{[round(t['close'], 2) for t in ticks[-10:]]}

Rules:
- RSI < 30 = oversold (potential BUY)
- RSI > 70 = overbought (potential SELL)
- Price below VWAP + bearish sentiment = stronger SELL signal
- Price above VWAP + bullish sentiment = stronger BUY signal
- If signals are mixed or unclear, direction should be HOLD

Respond with ONLY this JSON:
{{
  "direction": "BUY" | "SELL" | "HOLD",
  "confidence": <float 0.0 to 1.0>,
  "size_pct": <float 0.01 to 0.05>,
  "reasoning": "<under 200 chars>"
}}
"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system="You are a quantitative trading strategy agent. Return valid JSON only.",
        messages=[{"role": "user", "content": context}]
    )

    import re
    raw = response.content[0].text.strip()
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in response: {raw!r}")

    data = json.loads(match.group())
    return {
        "symbol": symbol,
        "direction": data["direction"],
        "confidence": float(data["confidence"]),
        "size_pct": float(data["size_pct"]),
        "reasoning": data["reasoning"],
        "price": current_price,
        "rsi": rsi,
        "sentiment": sentiment["avg"],
    }

# --- DB write ---

async def write_proposal(pool, proposal: dict):
    await pool.execute("""
        INSERT INTO trade_proposals (time, symbol, direction, size, confidence, reasoning, status)
        VALUES (NOW(), $1, $2, $3, $4, $5, 'PENDING')
    """,
        proposal["symbol"],
        proposal["direction"],
        proposal["size_pct"],
        proposal["confidence"],
        proposal["reasoning"],
    )

# --- Main loop ---

async def run(interval: int = 120):
    pool = await get_pool()
    logger.info("Strategy agent started.")

    while True:
        for symbol in SYMBOLS:
            try:
                ticks = await fetch_ticks(pool, symbol)
                if len(ticks) < 5:
                    logger.warning(f"[{symbol}] Not enough ticks yet ({len(ticks)}), skipping.")
                    continue

                closes = [t["close"] for t in ticks]
                rsi = compute_rsi(closes)
                vwap = compute_vwap(ticks)
                sentiment = await fetch_sentiment(pool, symbol)

                logger.info(f"[{symbol}] price={closes[-1]} rsi={rsi} vwap={round(vwap,2) if vwap else 'N/A'} sentiment={sentiment['avg']} ({sentiment['label']})")

                proposal = await generate_proposal(symbol, ticks, sentiment, rsi, vwap)
                await write_proposal(pool, proposal)

                logger.info(
                    f"[{symbol}] → {proposal['direction']} "
                    f"confidence={proposal['confidence']} "
                    f"reason: {proposal['reasoning']}"
                )

            except Exception as e:
                logger.error(f"[{symbol}] Strategy error: {e}")

        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(run())
