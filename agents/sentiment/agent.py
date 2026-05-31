import asyncio
import json
import logging
from datetime import datetime, timezone
from core.db import get_pool
from agents.sentiment.sources import fetch_rss, fetch_fear_and_greed
from agents.sentiment.scorer import score_article

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("sentiment-agent")

async def write_score(pool, symbol: str, score: float, source: str, headline: str, llm_used: bool, tokens: int = 0):
    await pool.execute("""
        INSERT INTO sentiment_scores (time, symbol, score, source, headline, llm_used, tokens_used)
        VALUES (NOW(), $1, $2, $3, $4, $5, $6)
    """, symbol, score, source, headline[:200], llm_used, tokens)

async def run(interval: int = 300):  # runs every 5 minutes
    pool = await get_pool()
    llm_calls = 0
    rule_calls = 0

    while True:
        logger.info("--- Sentiment cycle starting ---")

        # Fear & Greed — market-wide signal, write for both symbols
        try:
            fng = await fetch_fear_and_greed()
            for symbol in ["BTC", "ETH"]:
                await write_score(pool, symbol, fng["score"], "fear-and-greed",
                                  f"Fear & Greed: {fng['label']} ({fng['raw']})", False)
            logger.info(f"Fear & Greed: {fng['label']} ({fng['raw']}) → score={fng['score']:.2f}")
        except Exception as e:
            logger.error(f"Fear & Greed failed: {e}")

        # RSS articles
        try:
            articles = await fetch_rss()
            logger.info(f"Fetched {len(articles)} relevant articles")

            for article in articles:
                result = await score_article(article["text"])

                if result.use_llm:
                    llm_calls += 1
                else:
                    rule_calls += 1

                for symbol in article["symbols"]:
                    await write_score(pool, symbol, result.score,
                                      article["source"], article["headline"],
                                      result.use_llm)

                logger.info(
                    f"[{'LLM' if result.use_llm else 'RULE'}] "
                    f"{article['headline'][:60]}... → {result.score:.2f}"
                )

        except Exception as e:
            logger.error(f"RSS scoring failed: {e}")

        # Cost tracker log
        total = llm_calls + rule_calls
        saved_pct = round((rule_calls / total) * 100) if total else 0
        logger.info(f"Cost router: {rule_calls} rule-based, {llm_calls} LLM calls ({saved_pct}% saved)")

        await pool.execute("""
            INSERT INTO agent_events (time, agent, event_type, message, metadata)
            VALUES (NOW(), 'sentiment-agent', 'CYCLE_COMPLETE', 'Sentiment cycle done',
            $1::jsonb)
        """, json.dumps({"llm_calls": llm_calls, "rule_calls": rule_calls, "saved_pct": saved_pct}))

        logger.info(f"Sleeping {interval}s until next cycle...")
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(run())