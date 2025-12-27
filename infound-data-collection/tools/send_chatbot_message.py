"""
Publish a test chatbot batch message to RabbitMQ using the same config loader as consumers.

Examples:
  poetry run python tools/send_chatbot_message.py --env dev --creator-id 7495061956287171567 \
    --message "Hi *" --link "https://**"

  poetry run python tools/send_chatbot_message.py --env dev --creator-id 7495061956287171567 \
    --messages-json '[{"type":"text","content":"Hi *"},{"type":"link","content":"https://**"}]'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import quote_plus

import aio_pika
from aio_pika import ExchangeType

# Ensure project root is on sys.path so `common` can be imported when invoked directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.core.config import get_settings, initialize_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish a chatbot MQ message")
    parser.add_argument("--env", default="dev", choices=["dev", "stg", "pro"])
    parser.add_argument("--consumer", default="sample_chatbot", help="config consumer name")
    parser.add_argument("--region", default="MX")
    parser.add_argument("--creator-id", help="platformCreatorId (required unless tasks are provided)")
    parser.add_argument("--sample-id", default=None, help="sampleId (optional)")
    parser.add_argument("--product-id", default=None, help="platformProductId (optional)")
    parser.add_argument("--product-name", default=None, help="platformProductName (optional)")
    parser.add_argument("--campaign-name", default=None, help="platformCampaignName (optional)")
    parser.add_argument("--username", default=None, help="platformCreatorUsername (optional)")
    parser.add_argument("--whatsapp", default=None, help="creatorWhatsapp (optional)")
    parser.add_argument(
        "--message",
        action="append",
        default=[],
        help="text message content (repeatable)",
    )
    parser.add_argument(
        "--link",
        action="append",
        default=[],
        help="link message content (repeatable)",
    )
    parser.add_argument(
        "--messages-json",
        default=None,
        help="JSON array of message objects",
    )
    parser.add_argument(
        "--messages-file",
        default=None,
        help="path to JSON array of message objects",
    )
    parser.add_argument(
        "--tasks-json",
        default=None,
        help="JSON array of tasks (overrides per-task args)",
    )
    parser.add_argument(
        "--tasks-file",
        default=None,
        help="path to JSON array of tasks (overrides per-task args)",
    )
    parser.add_argument(
        "--routing-key",
        default=None,
        help="override routing key (default: '<prefix>.batch' derived from consumer binding key)",
    )
    return parser.parse_args()


def _default_batch_routing_key(binding_key: str) -> str:
    prefix = (binding_key or "").split("*", 1)[0].rstrip(".")
    if not prefix:
        return "chatbot.sample.batch"
    return f"{prefix}.batch"


def _load_json_value(value: Optional[str], label: str) -> Optional[Any]:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is not valid JSON: {exc}") from exc


def _load_json_file(path: Optional[str], label: str) -> Optional[Any]:
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Failed to read {label}: {exc}") from exc


def _normalize_tasks(value: Any, label: str) -> List[dict]:
    if isinstance(value, dict) and isinstance(value.get("tasks"), list):
        value = value["tasks"]
    if not isinstance(value, list):
        raise SystemExit(f"{label} must be a JSON array or an object with a 'tasks' array")
    return value


def _resolve_messages(args: argparse.Namespace) -> List[dict]:
    messages_value = _load_json_value(args.messages_json, "messages-json")
    if messages_value is None:
        messages_value = _load_json_file(args.messages_file, "messages-file")
    if messages_value is not None:
        if not isinstance(messages_value, list):
            raise SystemExit("messages must be a JSON array")
        return messages_value

    messages: List[dict] = []
    for text in args.message:
        if text:
            messages.append({"type": "text", "content": text})
    for link in args.link:
        if link:
            messages.append({"type": "link", "content": link})
    return messages


def _build_task(args: argparse.Namespace, messages: List[dict]) -> dict:
    if not args.creator_id:
        raise SystemExit("--creator-id is required when tasks are not provided")

    payload = {
        "region": str(args.region or "MX").upper(),
        "platformCreatorId": str(args.creator_id).strip(),
        "messages": messages,
    }
    if args.sample_id:
        payload["sampleId"] = str(args.sample_id).strip()
    if args.product_id:
        payload["platformProductId"] = str(args.product_id).strip()
    if args.product_name:
        payload["platformProductName"] = str(args.product_name).strip()
    if args.campaign_name:
        payload["platformCampaignName"] = str(args.campaign_name).strip()
    if args.username:
        payload["platformCreatorUsername"] = str(args.username).strip()
    if args.whatsapp:
        payload["creatorWhatsapp"] = str(args.whatsapp).strip()
    return payload


async def publish() -> None:
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
    batch_routing_key = args.routing_key or _default_batch_routing_key(settings.RABBITMQ_ROUTING_KEY)

    tasks_value = _load_json_value(args.tasks_json, "tasks-json")
    if tasks_value is None:
        tasks_value = _load_json_file(args.tasks_file, "tasks-file")

    if tasks_value is not None:
        tasks = _normalize_tasks(tasks_value, "tasks")
    else:
        messages = _resolve_messages(args)
        if not messages:
            raise SystemExit("messages is required")
        tasks = [_build_task(args, messages)]

    if not tasks:
        raise SystemExit("tasks is empty")

    batch_id = f"BATCH-{str(uuid.uuid4()).upper()}"

    conn = await aio_pika.connect_robust(amqp_url, timeout=20, heartbeat=60)
    async with conn:
        channel = await conn.channel()
        exchange = await channel.declare_exchange(exchange_name, ExchangeType.TOPIC, durable=True)

        body_bytes = json.dumps(tasks, ensure_ascii=False).encode("utf-8")
        msg = aio_pika.Message(
            body=body_bytes,
            message_id=batch_id,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
            headers={"task_id": batch_id, "task_count": len(tasks)},
        )
        await exchange.publish(msg, routing_key=batch_routing_key, mandatory=True)

    print(
        f"Published chatbot batch: exchange={exchange_name} rk={batch_routing_key} task_count={len(tasks)}"
    )
    print(json.dumps(tasks, ensure_ascii=False))


def main() -> None:
    asyncio.run(publish())


if __name__ == "__main__":
    main()
