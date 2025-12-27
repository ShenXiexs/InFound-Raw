"""
Requeue messages from the chatbot dead-letter queue back to the main exchange.

Typical usage:
  poetry run python tools/requeue_chatbot_dlq.py --consumer sample_chatbot --env dev --limit 50
  poetry run python tools/requeue_chatbot_dlq.py --consumer sample_chatbot --env dev --limit 10 --routing-key chatbot.sample.retry
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import quote_plus

import aio_pika
from aio_pika import ExchangeType
from aio_pika.exceptions import QueueEmpty

# Ensure project root is on sys.path so `common` can be imported when invoked directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.core.config import get_settings, initialize_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Requeue chatbot DLQ messages")
    parser.add_argument("--env", default="dev", choices=["dev", "stg", "pro"])
    parser.add_argument("--consumer", default="sample_chatbot")
    parser.add_argument("--limit", type=int, default=50, help="max messages to requeue")
    parser.add_argument(
        "--routing-key",
        default=None,
        help="target routing key (default: chatbot.sample.retry or '<prefix>.retry')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="peek one message and exit without acking",
    )
    return parser.parse_args()


async def requeue() -> None:
    args = parse_args()
    initialize_settings(env_arg=args.env, consumer_arg=args.consumer)
    settings = get_settings()

    amqp_url = (
        f"amqp://{quote_plus(settings.RABBITMQ_USERNAME)}:"
        f"{quote_plus(settings.RABBITMQ_PASSWORD)}@"
        f"{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/"
        f"{quote_plus(settings.RABBITMQ_VHOST)}"
    )

    exchange_name = settings.RABBITMQ_EXCHANGE_NAME
    dlq_name = f"{settings.RABBITMQ_QUEUE_NAME}.dead"

    default_routing_key = "chatbot.sample.retry"
    if getattr(settings, "RABBITMQ_ROUTING_KEY", None):
        # If binding is like "chatbot.sample.*", use "chatbot.sample.retry".
        prefix = str(settings.RABBITMQ_ROUTING_KEY).split("*", 1)[0].rstrip(".")
        if prefix:
            default_routing_key = f"{prefix}.retry"
    target_routing_key = args.routing_key or default_routing_key

    conn = await aio_pika.connect_robust(amqp_url, timeout=20, heartbeat=60)
    async with conn:
        channel = await conn.channel()
        await channel.set_qos(prefetch_count=1)

        exchange = await channel.declare_exchange(
            exchange_name,
            ExchangeType.TOPIC,
            durable=True,
        )
        dlq = await channel.declare_queue(dlq_name, durable=True)

        requeued = 0
        while True:
            if args.dry_run and requeued >= 1:
                break
            if not args.dry_run and requeued >= max(args.limit, 0):
                break

            try:
                msg = await dlq.get(timeout=1, fail=False)
            except QueueEmpty:
                break

            if msg is None:
                break

            body_text = None
            try:
                body_text = msg.body.decode("utf-8")
            except Exception:
                body_text = None

            if args.dry_run:
                print("DLQ message_id:", msg.message_id)
                print("DLQ headers:", json.dumps(msg.headers or {}, ensure_ascii=False))
                print("DLQ body:", body_text or f"<{len(msg.body)} bytes>")
                await msg.reject(requeue=True)
                requeued += 1
                continue

            try:
                await exchange.publish(
                    aio_pika.Message(
                        body=msg.body,
                        message_id=msg.message_id,
                        headers=msg.headers,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        content_type=msg.content_type or "application/json",
                    ),
                    routing_key=target_routing_key,
                    mandatory=True,
                )
            except Exception as exc:
                print(f"Publish failed, keeping message in DLQ: {exc}")
                await msg.reject(requeue=True)
                break

            await msg.ack()
            requeued += 1

        print(
            f"Done. requeued={requeued} dlq={dlq_name} -> exchange={exchange_name} rk={target_routing_key}"
        )


def main() -> None:
    asyncio.run(requeue())


if __name__ == "__main__":
    main()

