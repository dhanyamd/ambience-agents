"""Central configuration, loaded from the environment (.env)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _f(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def _i(name: str, default: str) -> int:
    return int(os.getenv(name, default))


@dataclass(frozen=True)
class Config:
    # senses
    coinbase_ws_url: str = os.getenv("COINBASE_WS_URL", "wss://ws-feed.exchange.coinbase.com")
    product_id: str = os.getenv("PRODUCT_ID", "BTC-USD")

    # nervous system
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "crypto.trades")

    # two-stage funnel
    window_seconds: int = _i("WINDOW_SECONDS", "10")
    min_trades: int = _i("MIN_TRADES", "15")
    price_move_pct_threshold: float = _f("PRICE_MOVE_PCT_THRESHOLD", "0.15")
    imbalance_threshold: float = _f("IMBALANCE_THRESHOLD", "0.65")

    # brain
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")

    # escalation
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")


config = Config()
