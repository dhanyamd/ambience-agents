"""The escalation path: notify a human. This agent stays at the lowest trust
level — 'notify'. It never asks for approval to act and it never acts on the
market. It only tells you something happened.

If Telegram credentials are configured it sends there; otherwise it prints to
the terminal.
"""
import requests

from .config import config
from .models import WindowStats, Verdict

_SEVERITY_ICON = {"low": "🟢", "medium": "🟡", "high": "🔴"}


def _format(stats: WindowStats, verdict: Verdict) -> str:
    icon = _SEVERITY_ICON.get(verdict.severity, "⚪️")
    return (
        f"{icon} [{verdict.severity.upper()}] {verdict.headline}\n"
        f"{verdict.analysis}\n"
        f"— {stats.product_id} | move {stats.price_move_pct:+.3f}% | "
        f"imbalance {stats.imbalance:+.3f} | {stats.trade_count} trades / "
        f"{stats.window_seconds}s"
    )


def notify(stats: WindowStats, verdict: Verdict) -> None:
    text = _format(stats, verdict)
    if config.telegram_bot_token and config.telegram_chat_id:
        _send_telegram(text)
    else:
        print("\n" + "=" * 60)
        print("🔔 AMBIENT AGENT NOTIFICATION")
        print(text)
        print("=" * 60 + "\n")


def _send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": config.telegram_chat_id, "text": text},
            timeout=10,
        )
        if r.status_code != 200:
            print(f"[notifier] telegram failed ({r.status_code}): {r.text}")
    except requests.RequestException as e:
        print(f"[notifier] telegram error: {e}")
