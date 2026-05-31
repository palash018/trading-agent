# Trading Agent — Autonomous Multi-Agent Crypto Trading System

A production-grade multi-agent system that autonomously ingests live market data, scores financial sentiment, generates quantitative trade proposals, and enforces deterministic risk controls — all running concurrently as async agents with a live terminal observability dashboard.

> Built to demonstrate real-world AI agent orchestration: not a tutorial, not a demo — a system that runs continuously against live market data.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Orchestrator                          │
│                    (asyncio.gather)                          │
└──────┬──────────────┬──────────────┬──────────────┬─────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│   Data     │ │ Sentiment  │ │  Strategy  │ │   Risk     │
│   Agent    │ │   Agent    │ │   Agent    │ │   Agent    │
│            │ │            │ │            │ │            │
│ Binance WS │ │ RSS feeds  │ │ RSI + VWAP │ │ Confidence │
│ WebSocket  │ │ Fear&Greed │ │ + Claude   │ │ + Size     │
│ OHLCV →   │ │ Claude     │ │ Sonnet     │ │ + Daily    │
│ TimescaleDB│ │ Haiku      │ │ proposals  │ │ limit      │
└─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
      │              │              │              │
      └──────────────┴──────────────┴──────────────┘
                             │
                      ┌──────▼──────┐
                      │ TimescaleDB  │
                      │ Hypertables  │
                      └──────┬──────┘
                             │
                      ┌──────▼──────┐
                      │  FastAPI    │
                      │  REST layer │
                      └──────┬──────┘
                             │
                      ┌──────▼──────┐
                      │  Rich       │
                      │  Terminal   │
                      │  Dashboard  │
                      └─────────────┘
```

### Agent Breakdown

| Agent | Responsibility | LLM Used |
|---|---|---|
| **Data Agent** | Streams live OHLCV ticks via Binance WebSocket, writes to TimescaleDB hypertables with auto-reconnect | None |
| **Sentiment Agent** | Ingests RSS feeds + Fear & Greed Index, routes articles through rule-based classifier or Claude Haiku | Claude Haiku (ambiguous articles only) |
| **Strategy Agent** | Computes RSI + VWAP from live ticks, combines with sentiment, sends to Claude Sonnet for trade proposal | Claude Sonnet |
| **Risk Agent** | Validates proposals against confidence threshold, position size, daily trade limit — fully deterministic | None |

---

## Key Engineering Decisions

### 1. Rule-based LLM router in the sentiment agent
Most financial headlines contain strong signal keywords (crash, rally, ban, surge). Routing these through a keyword classifier before hitting the LLM reduces API calls by ~38% with no loss in signal quality. Only ambiguous articles go to Claude Haiku. This is the pattern production AI systems use to control inference costs at scale.

### 2. TimescaleDB hypertables over plain PostgreSQL
Market tick data is append-only and queried almost exclusively by time range and symbol. TimescaleDB's automatic time-based partitioning keeps these queries fast as data grows — a plain `LIMIT 30 ORDER BY time DESC` stays sub-millisecond even at millions of rows.

### 3. Deterministic risk checks, not LLM judgment
The risk agent uses zero LLMs. Confidence thresholds, position size limits, and daily trade caps are enforced with pure Python. LLMs are non-deterministic — you cannot trust them as a safety gateway for anything financial. Every rejection is logged to a structured audit table for full traceability.

### 4. Claude Sonnet reserved for complex reasoning only
Three of the four agents use no LLM at all, or use the cheapest available model (Haiku). Claude Sonnet is invoked only in the strategy agent where multi-variable reasoning (price + RSI + VWAP + sentiment) genuinely benefits from a capable model. This keeps the system cost under $10/month at continuous operation.

### 5. Async-first architecture throughout
All agents run concurrently via `asyncio.gather`. The data agent's WebSocket loop never blocks — DB writes are awaited separately. Backpressure from slow DB writes cannot stall the tick ingestion pipeline.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Market data | Binance WebSocket API |
| Time-series DB | TimescaleDB (PostgreSQL) |
| Async runtime | Python asyncio + asyncpg |
| LLM (routing) | Claude Haiku |
| LLM (strategy) | Claude Sonnet |
| Structured output | Pydantic models + JSON parsing |
| News ingestion | feedparser (RSS) + alternative.me Fear & Greed API |
| REST layer | FastAPI + uvicorn |
| Terminal UI | Python Rich |
| Infra | Docker Compose |

---

## Running Locally

### Prerequisites
- Python 3.12+
- Docker

### Setup

```bash
git clone https://github.com/palash018/trading-agent.git
cd trading-agent

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in ANTHROPIC_API_KEY in .env

docker compose up -d
PYTHONPATH=. python scripts/seed_historical.py
```

### Run

Open 3 terminals:

```bash
# Terminal 1 — all agents
python -m core.orchestrator

# Terminal 2 — REST API
uvicorn core.api:app --port 8000

# Terminal 3 — live dashboard
python core/dashboard.py
```

---

## Live Dashboard

```
╭─────────────── System Stats ───────────────╮╭──────────── Live Market Data ─────────────╮
│  Ticks ingested    213                     ││  BTCUSDT   $73,848.41   ▼ 0.004%          │
│  Sentiment scores  53                      ││  ETHUSDT    $2,020.32   ▼ 0.004%          │
│  LLM cost saved    38%                     │╰───────────────────────────────────────────╯
│  Approved trades   3                       │
│  Rejected trades   3                       │
╰────────────────────────────────────────────╯
╭──────────── Sentiment ─────────────────────╮╭──────────── Trade Proposals ───────────────╮
│  BTC  +0.00  LLM   17 years later...       ││  ETHUSDT  BUY  0.55  ⏳ PENDING            │
│  ETH  -0.70  RULE  Solana News: SoFi...    ││  BTCUSDT  HOLD 0.42  ❌ REJECTED           │
╰────────────────────────────────────────────╯╰───────────────────────────────────────────╯
╭──────────────────────── Risk Audit Log ────────────────────────────────────────────────╮
│  ❌ REJECTED   Confidence 0.45 below threshold | HOLD proposals are not executed       │
│  ✅ APPROVED   All checks passed. Mock execution: FILLED                               │
╰────────────────────────────────────────────────────────────────────────────────────────╯
```

---

## What's intentionally not here

- **Real trade execution** — the execution gateway is mocked. Connecting to Binance's live trading API is a one-line change; it's excluded because the strategy is not financially validated.
- **Local LLMs** — the dev machine (Ryzen 3 5300U, 8GB RAM) cannot run inference at useful speed. The architecture supports dropping in an Ollama endpoint; the router logic doesn't change.
- **Twitter/Reddit** — X API costs $100/month. RSS feeds from CoinDesk, CoinTelegraph, and Yahoo Finance provide equivalent signal for financial news with zero cost.

---

## Author

**Palash Tiwari** — [LinkedIn](https://linkedin.com/in/palash) · [GitHub](https://github.com/palash018)
