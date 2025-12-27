"""
Utility script to publish a sample MQ message using the same config as the consumer.

Usage:
  poetry run python tools/send_test_message.py --consumer portal_tiktok_sample_crawler --env dev --camel-case
  poetry run python tools/send_test_message.py --consumer portal_tiktok_sample_crawler_html --env dev
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import quote_plus

import aio_pika
from aio_pika import exceptions as aio_exceptions

# Ensure project root is on sys.path so `common` can be imported when invoked directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.core.config import get_settings, initialize_settings


def str2bool(value: str) -> bool:
    lowered = str(value).lower()
    if lowered in {"1", "true", "yes", "y", "t"}:
        return True
    if lowered in {"0", "false", "no", "n", "f"}:
        return False
    raise argparse.ArgumentTypeError("boolean value expected")


def build_message(args, settings) -> dict:
    scan_all = args.scan_all_pages if args.scan_all_pages is not None else not bool(args.campaign_id)
    max_pages = args.max_pages if args.max_pages and args.max_pages > 0 else None

    if args.camel_case:
        msg = {
            "tab": args.tab,
            "region": args.region or getattr(settings, "SAMPLE_DEFAULT_REGION", "MX"),
            "function": args.function,
            "scanAllPages": scan_all,
            "expandViewContent": args.expand_view_content,
            "viewLogistics": args.view_logistics,
            "exportExcel": args.export_excel,
        }
        if args.campaign_id:
            msg["campaignId"] = args.campaign_id
        if args.account_name:
            msg["accountName"] = args.account_name
        if max_pages is not None:
            msg["maxPages"] = max_pages
        return msg

    msg = {
        "tab": args.tab,
        "region": args.region or getattr(settings, "SAMPLE_DEFAULT_REGION", "MX"),
        "function": args.function,
        "scan_all_pages": scan_all,
        "expand_view_content": args.expand_view_content,
        "view_logistics": args.view_logistics,
        "export_excel": args.export_excel,
    }
    if args.campaign_id:
        msg["campaign_id"] = args.campaign_id
    if args.account_name:
        msg["account_name"] = args.account_name
    if max_pages is not None:
        msg["max_pages"] = max_pages
    return msg


def _extract_tabs(message: dict) -> list[str]:
    raw = None
    if isinstance(message.get("tabs"), list):
        raw = message.get("tabs")
    else:
        raw = [message.get("tab")]
        if not raw[0]:
            raw = [message.get("tabName")]
    return [str(item).strip().lower() for item in (raw or []) if item is not None and str(item).strip()]


def _select_routing(settings, message: dict) -> tuple[str, str]:
    """
    Choose routing key + queue name.

    For `portal_tiktok_sample_crawler`, we split by tab:
    - tabs=['completed'] -> completed queue
    - otherwise -> other queue
    """
    tabs = _extract_tabs(message)
    is_completed = len(tabs) == 1 and tabs[0] == "completed"

    completed_rk = getattr(settings, "RABBITMQ_COMPLETED_ROUTING_KEY", None)
    completed_q = getattr(settings, "RABBITMQ_COMPLETED_QUEUE_NAME", None)
    other_rk = getattr(settings, "RABBITMQ_OTHER_ROUTING_KEY", None)
    other_q = getattr(settings, "RABBITMQ_OTHER_QUEUE_NAME", None)

    if completed_rk and completed_q and other_rk and other_q:
        return (completed_rk, completed_q) if is_completed else (other_rk, other_q)

    # Fallback: single-queue mode.
    return settings.RABBITMQ_ROUTING_KEY, settings.RABBITMQ_QUEUE_NAME


async def publish_message(message: dict) -> None:
    settings = get_settings()
    amqp_url = (
        f"amqp://{quote_plus(settings.RABBITMQ_USERNAME)}:"
        f"{quote_plus(settings.RABBITMQ_PASSWORD)}@"
        f"{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/"
        f"{quote_plus(settings.RABBITMQ_VHOST)}"
    )
    exchange_name = settings.RABBITMQ_EXCHANGE_NAME
    routing_key, queue_name = _select_routing(settings, message)
    dlx_name = f"{exchange_name}.dlx"
    dl_routing_key = f"{routing_key}.dead"
    queue_args = {
        "x-dead-letter-exchange": dlx_name,
        "x-dead-letter-routing-key": dl_routing_key,
    }

    conn = await aio_pika.connect_robust(amqp_url, timeout=15, heartbeat=30)
    async with conn:
        channel = await conn.channel()
        exchange = await channel.declare_exchange(exchange_name, aio_pika.ExchangeType.DIRECT, durable=True)
        # Match consumer behavior: declare DLX + main queue (with DLQ).
        dlx_exchange = await channel.declare_exchange(dlx_name, aio_pika.ExchangeType.DIRECT, durable=True)
        dlq = await channel.declare_queue(f"{queue_name}.dead", durable=True)
        await dlq.bind(dlx_exchange, routing_key=dl_routing_key)

        queue = await channel.declare_queue(queue_name, durable=True, arguments=queue_args)
        await queue.bind(exchange, routing_key=routing_key)

        before_res = queue.declaration_result
        before = getattr(before_res, "message_count", None)
        before_consumers = getattr(before_res, "consumer_count", None)

        try:
            await exchange.publish(
                aio_pika.Message(body=json.dumps(message).encode()),
                routing_key=routing_key,
                mandatory=True,
            )
        except aio_exceptions.DeliveryError as exc:
            print("Publish failed: message was unroutable or delivery failed", exc)
            return

        # Re-declare to fetch latest backlog.
        queue_after = await channel.declare_queue(queue_name, durable=True, arguments=queue_args)
        after_res = queue_after.declaration_result
        after = getattr(after_res, "message_count", None)
        after_consumers = getattr(after_res, "consumer_count", None)

        print(f"Published message to {exchange_name}/{routing_key}")
        print(f"Queue '{queue_name}' backlog: {before} -> {after} | consumers: {before_consumers} -> {after_consumers}")
        print("Payload:", json.dumps(message, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Publish a sample MQ message")
    parser.add_argument("--env", default="dev", help="env name, e.g. dev/stg/pro")
    parser.add_argument("--consumer", default="portal_tiktok_sample_crawler", help="consumer name to load config")
    parser.add_argument("--campaign-id", help="optional campaign_id")
    parser.add_argument("--account-name", help="optional account name")
    parser.add_argument("--region", help="region code, defaults to config SAMPLE_DEFAULT_REGION")
    parser.add_argument("--tab", default="all", help="tab name, e.g. all/review/ready")
    parser.add_argument("--function", default="sample", help="logical function of the task, defaults to sample")
    parser.add_argument("--max-pages", type=int, help="optional max pages to crawl (maxPages/max_pages)")
    parser.add_argument("--scan-all-pages", type=str2bool, nargs="?", const=True, default=None, help="scan all pages; default: true if no campaign_id")
    parser.add_argument("--expand-view-content", type=str2bool, nargs="?", const=True, default=True, help="whether to click View content")
    parser.add_argument("--view-logistics", type=str2bool, nargs="?", const=True, default=True, help="whether to click View logistics")
    parser.add_argument("--export-excel", type=str2bool, nargs="?", const=True, default=False, help="whether to export excel")
    parser.add_argument(
        "--camel-case",
        action="store_true",
        help="send message using camelCase field names (recommended for portal_tiktok_sample_crawler)",
    )
    args = parser.parse_args()

    initialize_settings(env_arg=args.env, consumer_arg=args.consumer)
    settings = get_settings()
    message = build_message(args, settings)
    asyncio.run(publish_message(message))


if __name__ == "__main__":
    main()
