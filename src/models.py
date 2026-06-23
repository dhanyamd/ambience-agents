"""Shared data shapes passed between components."""
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class Trade:
    """A single trade ("match") from the Coinbase feed."""
    product_id: str
    price: float
    size: float
    side: str       # 'buy' or 'sell' (side of the resting/maker order)
    time: str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Trade":
        return Trade(
            product_id=d["product_id"],
            price=float(d["price"]),
            size=float(d["size"]),
            side=d["side"],
            time=d["time"],
        )


@dataclass
class WindowStats:
    """Stage-1 output: cheap, stateless math over one time window."""
    product_id: str
    window_seconds: int
    trade_count: int
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    price_move_pct: float     # signed % move open -> close
    buy_volume: float
    sell_volume: float
    total_volume: float
    imbalance: float          # signed (buy - sell) / total, range -1..1
    start_time: str
    end_time: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Verdict:
    """Stage-2 output: the LLM's structured judgment."""
    is_significant: bool
    severity: str             # 'low' | 'medium' | 'high'
    headline: str
    analysis: str
