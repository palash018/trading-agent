import asyncio
import logging
from agents.data.ingestion import run as run_data
from agents.sentiment.agent import run as run_sentiment
from agents.strategy.agent import run as run_strategy
from agents.risk.agent import run as run_risk

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("orchestrator")

async def main():
    logger.info("🚀 Starting all agents...")
    await asyncio.gather(
        run_data(),
        run_sentiment(interval=300),
        run_strategy(interval=120),
        run_risk(interval=120),
    )

if __name__ == "__main__":
    asyncio.run(main())
