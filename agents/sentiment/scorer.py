import os
import json
import re
import anthropic
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

class SentimentResult(BaseModel):
    score: float = Field(..., ge=-1.0, le=1.0)
    reasoning: str
    use_llm: bool = True

SIMPLE_KEYWORDS = {
    "bullish": 0.6, "surge": 0.6, "rally": 0.5, "gain": 0.4,
    "bearish": -0.6, "crash": -0.7, "dump": -0.6, "drop": -0.4,
    "hack": -0.8, "ban": -0.7, "sec": -0.4, "lawsuit": -0.5,
    "outflow": -0.5, "inflow": 0.5, "record": 0.3, "fear": -0.5,
}

def rule_based_score(text: str) -> float | None:
    text_lower = text.lower()
    scores = [v for k, v in SIMPLE_KEYWORDS.items() if k in text_lower]
    if not scores:
        return None
    return max(scores, key=abs)

def extract_json(raw: str) -> dict:
    """Strip markdown fences and extract first JSON object found."""
    # Remove ```json ... ``` or ``` ... ```
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    # Find first { ... } block
    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in: {raw!r}")
    return json.loads(match.group())

async def score_article(text: str) -> SentimentResult:
    quick = rule_based_score(text)
    if quick is not None:
        return SentimentResult(score=quick, reasoning="rule-based keyword match", use_llm=False)

    try:
        response = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system="You are a financial sentiment analyzer. Respond with a JSON object only. No markdown, no extra text.",
            messages=[{
                "role": "user",
                "content": (
                    f"Analyze this crypto/financial news.\n\n"
                    f"Text: {text[:300]}\n\n"
                    f'Return exactly this JSON: {{"score": <float -1.0 to 1.0>, "reasoning": "<under 100 chars>"}}'
                )
            }]
        )
        raw = response.content[0].text.strip()
        data = extract_json(raw)
        score = max(-1.0, min(1.0, float(data["score"])))
        return SentimentResult(score=score, reasoning=data.get("reasoning", ""), use_llm=True)

    except Exception as e:
        # Fallback to neutral rather than crashing the cycle
        return SentimentResult(score=0.0, reasoning=f"parse error: {e}", use_llm=True)
