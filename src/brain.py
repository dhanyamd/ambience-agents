"""Stage 2 of the funnel: the brain (local LLM via Ollama).

Only invoked for windows that survived Stage 1. We ask a local model to judge
whether the movement is genuinely worth a human's attention, and to return a
*structured* JSON verdict so downstream code can act on it reliably.
"""
import json

import ollama

from .config import config
from .models import WindowStats, Verdict

SYSTEM_PROMPT = """You are an ambient market-watching agent. You observe a live \
crypto trade stream and have ALREADY decided a time window is statistically \
unusual. Your job is to judge whether it is worth interrupting a human for, and \
to explain it in one or two crisp sentences a trader would respect.

You never give financial advice and you never suggest placing trades. You only \
describe what is happening and how notable it is.

Respond ONLY with JSON matching this schema:
{
  "is_significant": boolean,   // true only if a human should be notified now
  "severity": "low" | "medium" | "high",
  "headline": string,          // <= 80 chars, punchy summary
  "analysis": string           // 1-2 sentences explaining the window
}"""

# Structured-output schema handed to Ollama so the model is constrained to valid JSON.
_FORMAT = {
    "type": "object",
    "properties": {
        "is_significant": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
        "headline": {"type": "string"},
        "analysis": {"type": "string"},
    },
    "required": ["is_significant", "severity", "headline", "analysis"],
}


def _user_prompt(stats: WindowStats) -> str:
    return (
        f"Window for {stats.product_id} over {stats.window_seconds}s:\n"
        f"- trades: {stats.trade_count}\n"
        f"- price: open {stats.open_price}, close {stats.close_price}, "
        f"high {stats.high_price}, low {stats.low_price}\n"
        f"- price move: {stats.price_move_pct:+.3f}%\n"
        f"- volume: buy {stats.buy_volume}, sell {stats.sell_volume}, "
        f"total {stats.total_volume}\n"
        f"- buy/sell imbalance: {stats.imbalance:+.3f} (range -1..1)\n\n"
        f"Is this worth notifying a human about right now?"
    )


class Brain:
    def __init__(self):
        self._client = ollama.Client(host=config.ollama_host)
        self._model = config.ollama_model

    def analyze(self, stats: WindowStats) -> Verdict:
        resp = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(stats)},
            ],
            format=_FORMAT,
            options={"temperature": 0.2},
        )
        raw = resp["message"]["content"]
        data = json.loads(raw)
        return Verdict(
            is_significant=bool(data.get("is_significant", False)),
            severity=str(data.get("severity", "low")),
            headline=str(data.get("headline", "")).strip(),
            analysis=str(data.get("analysis", "")).strip(),
        )
