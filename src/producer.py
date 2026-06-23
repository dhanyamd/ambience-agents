"""The senses: stream Coinbase trades into Kafka.

Connects to Coinbase's public WebSocket, subscribes to the `matches` channel
(individual trades), and publishes each trade onto a Kafka topic. This is the
only component that knows about the event *source* — swap this file to point
the agent at a different stream.
"""
import json
import signal
import sys
import time

import websocket
from kafka import KafkaProducer

from .config import config
from .models import Trade

_running = True


def _on_sigint(signum, frame):
    global _running
    _running = False


def _make_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=config.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        linger_ms=50,
        acks=1,
    )


def run() -> None:
    signal.signal(signal.SIGINT, _on_sigint)
    producer = _make_producer()
    sub = {
        "type": "subscribe",
        "product_ids": [config.product_id],
        "channels": ["matches"],
    }

    print(f"[producer] connecting to {config.coinbase_ws_url} for {config.product_id}")
    published = 0

    while _running:
        ws = None
        try:
            ws = websocket.create_connection(config.coinbase_ws_url, timeout=30)
            ws.send(json.dumps(sub))
            print(f"[producer] subscribed; publishing to topic '{config.kafka_topic}'")

            while _running:
                raw = ws.recv()
                if not raw:
                    continue
                msg = json.loads(raw)
                # 'match' = a real trade; 'last_match' is the snapshot on subscribe.
                if msg.get("type") not in ("match", "last_match"):
                    continue
                try:
                    trade = Trade.from_dict(msg)
                except (KeyError, ValueError):
                    continue

                producer.send(
                    config.kafka_topic,
                    key=trade.product_id,
                    value=trade.to_dict(),
                )
                published += 1
                if published % 100 == 0:
                    print(f"[producer] published {published} trades "
                          f"(last: {trade.side} {trade.size} @ {trade.price})")
        except websocket.WebSocketException as e:
            print(f"[producer] websocket error: {e}; reconnecting in 3s")
            time.sleep(3)
        except Exception as e:  # noqa: BLE001 - keep the senses alive
            print(f"[producer] unexpected error: {e}; reconnecting in 3s")
            time.sleep(3)
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    print("[producer] flushing and shutting down...")
    producer.flush()
    producer.close()
    sys.exit(0)


if __name__ == "__main__":
    run()
