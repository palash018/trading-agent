import asyncio
import json
import logging
import os
from dotenv import load_dotenv
from core.db import get_pool

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("risk-agent")

MAX_CONFIDENCE_THRESHOLD = 0.50
MAX_DAILY_TRADES = 10
MAX_SIZE_PCT = 0.05
MIN_SIZE_PCT = 0.01

_daily_trade_count = 0

def check_confidence(proposal: dict) -> tuple[bool, str]:
    if proposal["confidence"] < MAX_CONFIDENCE_THRESHOLD:
        return False, f"Confidence {proposal['confidence']} below threshold {MAX_CONFIDENCE_THRESHOLD}"
    return True, "confidence OK"

def check_direction(proposal: dict) -> tuple[bool, str]:
    if proposal["direction"] == "HOLD":
        return False, "HOLD proposals are not executed"
    if proposal["direction"] not in ["BUY", "SELL"]:
        return False, f"Unknown direction: {proposal['direction']}"
    return True, "direction OK"

def check_size(proposal: dict) -> tuple[bool, str]:
    size = proposal["size"]
    if size < MIN_SIZE_PCT:
        return False, f"Size {size} below minimum {MIN_SIZE_PCT}"
    if size > MAX_SIZE_PCT:
        return False, f"Size {size} exceeds maximum {MAX_SIZE_PCT}"
    return True, "size OK"

def check_daily_limit() -> tuple[bool, str]:
    global _daily_trade_count
    if _daily_trade_count >= MAX_DAILY_TRADES:
        return False, f"Daily trade limit {MAX_DAILY_TRADES} reached"
    return True, f"daily count {_daily_trade_count}/{MAX_DAILY_TRADES} OK"

async def mock_execute(proposal: dict) -> dict:
    return {
        "status": "FILLED",
        "symbol": proposal["symbol"],
        "direction": proposal["direction"],
        "size_pct": proposal["size"],
        "mock": True,
    }

async def process_proposal(pool, proposal: dict):
    global _daily_trade_count

    checks = {
        "confidence": check_confidence(proposal),
        "direction": check_direction(proposal),
        "size": check_size(proposal),
        "daily_limit": check_daily_limit(),
    }

    all_passed = all(v[0] for v in checks.values())
    failed = {k: v[1] for k, v in checks.items() if not v[0]}

    if all_passed:
        execution = await mock_execute(proposal)
        _daily_trade_count += 1
        decision = "APPROVED"
        reason = f"All checks passed. Mock execution: {execution['status']}"
        logger.info(
            f"✅ APPROVED [{proposal['symbol']}] {proposal['direction']} "
            f"size={proposal['size']} confidence={proposal['confidence']}"
        )
    else:
        decision = "REJECTED"
        reason = " | ".join(failed.values())
        logger.info(
            f"❌ REJECTED [{proposal['symbol']}] {proposal['direction']} "
            f"— {reason}"
        )

    # Update proposal status using subquery instead of LIMIT
    await pool.execute("""
        UPDATE trade_proposals SET status = $1
        WHERE id IN (
            SELECT id FROM trade_proposals
            WHERE symbol = $2 AND status = 'PENDING'
            ORDER BY time DESC
            LIMIT 1
        )
    """, decision, proposal["symbol"])

    # Write audit log
    await pool.execute("""
        INSERT INTO risk_log (time, decision, reason, checks)
        VALUES (NOW(), $1, $2, $3::jsonb)
    """, decision, reason, json.dumps({k: v[1] for k, v in checks.items()}))

async def run(interval: int = 120):
    pool = await get_pool()
    logger.info("Risk agent started.")

    while True:
        rows = await pool.fetch("""
            SELECT symbol, direction, size, confidence, reasoning
            FROM trade_proposals
            WHERE status = 'PENDING'
            ORDER BY time DESC
        """)

        if not rows:
            logger.info("No pending proposals.")
        else:
            logger.info(f"Processing {len(rows)} pending proposal(s)...")
            for row in rows:
                await process_proposal(pool, dict(row))

        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(run())
