"""The agent loop. Reads trades from Kafka and runs the two-stage funnel:

    Kafka trades
        -> Stage 1: window + cheap math (funnel.py)        [most windows die here]
        -> Stage 1 thresholds tripped?
        -> Stage 2: local LLM judgment (brain.py)          [expensive, rare]
        -> LLM says significant?
        -> notify a human (notifier.py)                    [escalation path]

This is the "brain stem": it never sleeps, never trades, and only escalates the
high-signal moments.
"""
import json
import signal
import time

from kafka import KafkaConsumer

from .config import config
from .funnel import WindowAggregator, is_interesting
from .models import Trade
from .brain import Brain
from .notifier import notify

_running = True


def _on_sigint(signum, frame):
    global _running
    _running = False


def _make_consumer() -> KafkaConsumer:
    return KafkaConsumer(
        config.kafka_topic,
        bootstrap_servers=config.kafka_bootstrap_servers,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
        group_id="ambient-agent",
        consumer_timeout_ms=1000,  # let the loop breathe so SIGINT is responsive
    )


def run() -> None:
    signal.signal(signal.SIGINT, _on_sigint)

    print(f"[agent] starting two-stage funnel | window={config.window_seconds}s "
          f"min_trades={config.min_trades} "
          f"move>={config.price_move_pct_threshold}% "
          f"imbalance>={config.imbalance_threshold}")
    print(f"[agent] brain: ollama '{config.ollama_model}' @ {config.ollama_host}")

    consumer = _make_consumer()
    aggregator = WindowAggregator(config.window_seconds)
    brain = Brain()

    windows_sealed = 0
    windows_escalated = 0
    notifications = 0

    def handle_window(stats):
        nonlocal windows_sealed, windows_escalated, notifications
        if stats is None:
            return
        windows_sealed += 1
        # Stage 1: cheap filter — discard the boring majority for free.
        if not is_interesting(stats):
            return
        windows_escalated += 1
        print(f"[agent] stage-1 tripped (window #{windows_sealed}): "
              f"move {stats.price_move_pct:+.3f}%, imbalance {stats.imbalance:+.3f}, "
              f"{stats.trade_count} trades -> asking the brain")
        # Stage 2: the expensive LLM, reserved for high-signal windows only.
        try:
            verdict = brain.analyze(stats)
        except Exception as e:  # noqa: BLE001 - never let one window kill the agent
            print(f"[agent] brain error: {e}")
            return
        if verdict.is_significant:
            notifications += 1
            notify(stats, verdict)
        else:
            print(f"[agent] brain dismissed it: {verdict.headline!r}")

    while _running:
        try:
            for record in consumer:
                if not _running:
                    break
                trade = Trade.from_dict(record.value)
                sealed = aggregator.add(trade, time.time())
                handle_window(sealed)
        except Exception as e:  # noqa: BLE001 - keep the agent resident
            print(f"[agent] consumer error: {e}; retrying in 2s")
            time.sleep(2)

    # Drain the final partial window on shutdown.
    handle_window(aggregator.flush())
    print(f"[agent] shutting down. sealed={windows_sealed} "
          f"escalated={windows_escalated} notified={notifications}")
    consumer.close()


if __name__ == "__main__":
    run()
