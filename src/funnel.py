"""Stage 1 of the funnel: cheap, stateless math.

This is "the single most important idea in this build". Hundreds of trades per
second hit the stream, but the LLM is expensive. So we bucket trades into fixed
time windows, compute a handful of simple metrics per window, and let cheap
thresholds discard the boring majority for free. Only windows that trip a
threshold are allowed to reach Stage 2 (the LLM).
"""
from typing import List, Optional

from .config import config
from .models import Trade, WindowStats


class WindowAggregator:
    """Accumulates trades into a fixed wall-clock time window.

    Call `add()` for every trade. When a trade arrives that belongs to a new
    window, the previous window is sealed and returned as WindowStats.
    """

    def __init__(self, window_seconds: int):
        self.window_seconds = window_seconds
        self._bucket_start: Optional[float] = None
        self._trades: List[Trade] = []

    def add(self, trade: Trade, now: float) -> Optional[WindowStats]:
        if self._bucket_start is None:
            self._bucket_start = now

        sealed: Optional[WindowStats] = None
        if now - self._bucket_start >= self.window_seconds:
            sealed = self._seal()
            self._bucket_start = now
            self._trades = []

        self._trades.append(trade)
        return sealed

    def flush(self) -> Optional[WindowStats]:
        if self._trades:
            stats = self._seal()
            self._trades = []
            self._bucket_start = None
            return stats
        return None

    def _seal(self) -> Optional[WindowStats]:
        if not self._trades:
            return None
        trades = self._trades
        prices = [t.price for t in trades]
        open_price = trades[0].price
        close_price = trades[-1].price
        buy_volume = sum(t.size for t in trades if t.side == "buy")
        sell_volume = sum(t.size for t in trades if t.side == "sell")
        total_volume = buy_volume + sell_volume

        price_move_pct = ((close_price - open_price) / open_price * 100.0) if open_price else 0.0
        imbalance = ((buy_volume - sell_volume) / total_volume) if total_volume else 0.0

        return WindowStats(
            product_id=trades[0].product_id,
            window_seconds=self.window_seconds,
            trade_count=len(trades),
            open_price=open_price,
            close_price=close_price,
            high_price=max(prices),
            low_price=min(prices),
            price_move_pct=round(price_move_pct, 4),
            buy_volume=round(buy_volume, 6),
            sell_volume=round(sell_volume, 6),
            total_volume=round(total_volume, 6),
            imbalance=round(imbalance, 4),
            start_time=trades[0].time,
            end_time=trades[-1].time,
        )


def is_interesting(stats: WindowStats) -> bool:
    """The cheap filter. Returns True only if a window deserves the LLM.

    A window must clear a minimum trade count (skip thin/illiquid windows),
    then trip EITHER a meaningful price move OR a strong buy/sell imbalance.
    Tune the thresholds in .env.
    """
    if stats.trade_count < config.min_trades:
        return False
    if abs(stats.price_move_pct) >= config.price_move_pct_threshold:
        return True
    if abs(stats.imbalance) >= config.imbalance_threshold:
        return True
    return False
