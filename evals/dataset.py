"""Labeled evaluation dataset for the ambient agent.

Each case is a market window with two human-provided labels:

  - stage1_should_trip: should the cheap Stage-1 filter let this through?
      Tests the threshold config in funnel.py.

  - notify_worthy: would a human actually want a 🔔 for this?
      This is the Stage-2 target. The LLM's job is to APPROVE genuinely
      notable windows and REJECT the noisy ones that merely tripped Stage 1.
      (Cases where stage1_should_trip is False have notify_worthy=False too,
      since the brain never sees windows that don't pass Stage 1.)

The numbers are synthetic but chosen to mirror real BTC-USD behaviour around a
~65,000 price level with 10-second windows.
"""
from dataclasses import dataclass
from typing import List

from src.models import WindowStats


@dataclass
class EvalCase:
    name: str
    description: str
    stats: WindowStats
    stage1_should_trip: bool
    notify_worthy: bool


def _w(name, desc, *, trades, open_p, close_p, high, low,
       buy_vol, sell_vol, trip, notify) -> EvalCase:
    total = buy_vol + sell_vol
    move = ((close_p - open_p) / open_p * 100.0) if open_p else 0.0
    imbalance = ((buy_vol - sell_vol) / total) if total else 0.0
    stats = WindowStats(
        product_id="BTC-USD",
        window_seconds=10,
        trade_count=trades,
        open_price=open_p,
        close_price=close_p,
        high_price=high,
        low_price=low,
        price_move_pct=round(move, 4),
        buy_volume=round(buy_vol, 6),
        sell_volume=round(sell_vol, 6),
        total_volume=round(total, 6),
        imbalance=round(imbalance, 4),
        start_time="2026-06-23T00:00:00Z",
        end_time="2026-06-23T00:00:10Z",
    )
    return EvalCase(name, desc, stats, trip, notify)


DATASET: List[EvalCase] = [
    # --- Should be FILTERED by Stage 1 (never reach the brain) ---
    _w("calm_flat",
       "Quiet balanced tape, price basically flat.",
       trades=22, open_p=65000.0, close_p=65003.0, high=65010.0, low=64995.0,
       buy_vol=1.1, sell_vol=1.0, trip=False, notify=False),
    _w("thin_window",
       "Only a few trades — illiquid, below MIN_TRADES.",
       trades=4, open_p=65000.0, close_p=65120.0, high=65120.0, low=65000.0,
       buy_vol=0.3, sell_vol=0.05, trip=False, notify=False),
    _w("micro_drift",
       "Tiny drift, well under the move threshold, balanced flow.",
       trades=40, open_p=65000.0, close_p=65040.0, high=65050.0, low=64990.0,
       buy_vol=2.0, sell_vol=1.9, trip=False, notify=False),

    # --- Should PASS Stage 1 but the brain should REJECT (noise that tripped math) ---
    _w("barely_over_move",
       "Just over the move threshold but choppy and balanced — not real news.",
       trades=30, open_p=65000.0, close_p=65105.0, high=65140.0, low=64970.0,
       buy_vol=2.1, sell_vol=2.0, trip=True, notify=False),
    _w("imbalance_low_volume",
       "Strong imbalance but on trivial volume — statistically loud, materially nothing.",
       trades=18, open_p=65000.0, close_p=65010.0, high=65015.0, low=64998.0,
       buy_vol=0.12, sell_vol=0.01, trip=True, notify=False),

    # --- Should PASS Stage 1 and the brain should APPROVE (real, notify-worthy) ---
    _w("sharp_rally",
       "Sharp, sustained rally on heavy one-sided buying.",
       trades=120, open_p=65000.0, close_p=65520.0, high=65540.0, low=64990.0,
       buy_vol=14.0, sell_vol=3.0, trip=True, notify=True),
    _w("flash_dump",
       "Aggressive sell-off, price gaps down on heavy sell volume.",
       trades=140, open_p=65000.0, close_p=64480.0, high=65010.0, low=64450.0,
       buy_vol=2.5, sell_vol=16.0, trip=True, notify=True),
    _w("buy_wall_sweep",
       "Overwhelming buy imbalance on real volume, price ticking up.",
       trades=95, open_p=65000.0, close_p=65210.0, high=65230.0, low=64995.0,
       buy_vol=11.0, sell_vol=1.2, trip=True, notify=True),
]
