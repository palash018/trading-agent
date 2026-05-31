import json
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.db import get_pool

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/ticks/{symbol}")
async def get_ticks(symbol: str, limit: int = 30):
    pool = await get_pool()
    rows = await pool.fetch("""
        SELECT time, close, volume FROM market_ticks
        WHERE symbol = $1 ORDER BY time DESC LIMIT $2
    """, symbol.upper(), limit)
    return [{"time": str(r["time"]), "close": r["close"], "volume": r["volume"]} for r in reversed(rows)]

@app.get("/sentiment/{symbol}")
async def get_sentiment(symbol: str):
    pool = await get_pool()
    rows = await pool.fetch("""
        SELECT time, score, source, llm_used, headline FROM sentiment_scores
        WHERE symbol = $1 ORDER BY time DESC LIMIT 20
    """, symbol.upper())
    return [{"time": str(r["time"]), "score": r["score"], "source": r["source"],
             "llm_used": r["llm_used"], "headline": r["headline"]} for r in rows]

@app.get("/proposals")
async def get_proposals():
    pool = await get_pool()
    rows = await pool.fetch("""
        SELECT time, symbol, direction, confidence, size, reasoning, status
        FROM trade_proposals ORDER BY time DESC LIMIT 20
    """)
    return [dict(r) | {"time": str(r["time"])} for r in rows]

@app.get("/risk")
async def get_risk_log():
    pool = await get_pool()
    rows = await pool.fetch("""
        SELECT time, decision, reason, checks FROM risk_log
        ORDER BY time DESC LIMIT 20
    """)
    return [{"time": str(r["time"]), "decision": r["decision"],
             "reason": r["reason"], "checks": r["checks"]} for r in rows]

@app.get("/stats")
async def get_stats():
    pool = await get_pool()
    tick_count = await pool.fetchval("SELECT COUNT(*) FROM market_ticks")
    sentiment_count = await pool.fetchval("SELECT COUNT(*) FROM sentiment_scores")
    llm_calls = await pool.fetchval("SELECT COUNT(*) FROM sentiment_scores WHERE llm_used = true")
    approved = await pool.fetchval("SELECT COUNT(*) FROM trade_proposals WHERE status = 'APPROVED'")
    rejected = await pool.fetchval("SELECT COUNT(*) FROM trade_proposals WHERE status = 'REJECTED'")
    return {
        "ticks": tick_count,
        "sentiment_scores": sentiment_count,
        "llm_calls": llm_calls,
        "rule_calls": sentiment_count - llm_calls,
        "approved_trades": approved,
        "rejected_trades": rejected,
    }
