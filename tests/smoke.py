"""Offline smoke test for the two-stage funnel.

Requires no Kafka, no network, no Ollama. It feeds synthetic trades through the
Stage-1 aggregator and asserts the cheap filter behaves: a calm window is
discarded, a spiking window is escalated.
"""
from src.funnel import WindowAggregator, is_interesting
from src.models import Trade


def _trade(price, size, side):
    return Trade(product_id="BTC-USD", price=price, size=size, side=side, time="t")


def _seal(trades):
    agg = WindowAggregator(window_seconds=10)
    t = 1000.0
    for tr in trades:
        agg.add(tr, t)
        t += 0.1  # all within the same 10s window
    return agg.flush()


def test_calm_window_is_filtered():
    # 20 tiny, balanced trades, price flat -> should NOT escalate.
    trades = []
    for i in range(20):
        side = "buy" if i % 2 == 0 else "sell"
        trades.append(_trade(price=65000.0 + (0.5 if i % 2 else -0.5), size=0.01, side=side))
    stats = _seal(trades)
    assert stats is not None
    assert stats.trade_count == 20
    assert not is_interesting(stats), "calm window should be filtered by Stage 1"
    return stats


def test_price_spike_escalates():
    # Strong upward move across the window -> SHOULD escalate.
    trades = [_trade(price=65000.0, size=0.05, side="buy")]
    for i in range(20):
        trades.append(_trade(price=65000.0 + i * 10, size=0.05, side="buy"))
    stats = _seal(trades)
    assert stats is not None
    assert abs(stats.price_move_pct) >= 0.15
    assert is_interesting(stats), "price spike should trip Stage 1"
    return stats


def test_imbalance_escalates():
    # Heavy one-sided buying, flat price -> SHOULD escalate on imbalance.
    trades = [_trade(price=65000.0, size=1.0, side="buy") for _ in range(20)]
    stats = _seal(trades)
    assert stats is not None
    assert stats.imbalance >= 0.65
    assert is_interesting(stats), "strong imbalance should trip Stage 1"
    return stats


if __name__ == "__main__":
    calm = test_calm_window_is_filtered()
    print(f"PASS calm window filtered: move={calm.price_move_pct:+.3f}% "
          f"imbalance={calm.imbalance:+.3f} -> escalate=False")
    spike = test_price_spike_escalates()
    print(f"PASS price spike escalates: move={spike.price_move_pct:+.3f}% -> escalate=True")
    imb = test_imbalance_escalates()
    print(f"PASS imbalance escalates: imbalance={imb.imbalance:+.3f} -> escalate=True")
    print("\nAll smoke tests passed. The two-stage funnel filters and escalates correctly.")
