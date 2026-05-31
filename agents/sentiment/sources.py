import feedparser
import httpx
from datetime import datetime, timezone

TRACKED = {"BTC": ["bitcoin", "btc"], "ETH": ["ethereum", "eth"]}

RSS_FEEDS = [
    "https://feeds.coindesk.com/rss",
    "https://cointelegraph.com/rss",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD,ETH-USD&region=US&lang=en-US",
]

def extract_symbols(text: str) -> list[str]:
    text_lower = text.lower()
    return [sym for sym, keywords in TRACKED.items() if any(k in text_lower for k in keywords)]

async def fetch_rss() -> list[dict]:
    articles = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                text = f"{title}. {summary}"
                symbols = extract_symbols(text)
                if not symbols:
                    continue
                articles.append({
                    "headline": title,
                    "text": text[:500],
                    "symbols": symbols,
                    "source": url.split("/")[2],
                    "time": datetime.now(tz=timezone.utc),
                })
        except Exception as e:
            print(f"RSS error {url}: {e}")
    return articles

async def fetch_fear_and_greed() -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        data = r.json()["data"][0]
        return {
            "score": (int(data["value"]) - 50) / 50,  # normalize to -1.0 to +1.0
            "label": data["value_classification"],     # e.g. "Fear", "Greed"
            "raw": int(data["value"]),
        }