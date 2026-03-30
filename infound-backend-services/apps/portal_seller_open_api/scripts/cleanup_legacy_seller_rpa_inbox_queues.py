from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Iterable

import aio_pika
from sqlalchemy import distinct, select

from apps.portal_seller_open_api.core.config import Settings
from core_base import SettingsFactory, get_logger
from shared_domain import DatabaseManager
from shared_domain.models.infound import IfIdentityUsers, SellerTkRpaTaskPlans


LOGGER = get_logger("cleanup_legacy_seller_rpa_inbox_queues")
LEGACY_QUEUE_PREFIX = "seller.rpa.user.inbox"


async def collect_target_user_ids(explicit_user_ids: Iterable[str] | None) -> list[str]:
    explicit = [str(user_id or "").strip() for user_id in explicit_user_ids or [] if str(user_id or "").strip()]
    if explicit:
        return sorted(set(explicit))

    async with DatabaseManager.get_session() as session:
        active_user_rows = await session.execute(
            select(distinct(IfIdentityUsers.id)).where(
                (IfIdentityUsers.deleted.is_(None)) | (IfIdentityUsers.deleted == 0)
            )
        )
        try:
            active_user_ids = {
                str(user_id or "").strip()
                for user_id in active_user_rows.scalars().all()
                if str(user_id or "").strip()
            }
        finally:
            active_user_rows.close()

        task_plan_rows = await session.execute(
            select(distinct(SellerTkRpaTaskPlans.user_id)).where(
                SellerTkRpaTaskPlans.user_id.is_not(None)
            )
        )
        try:
            task_plan_user_ids = {
                str(user_id or "").strip()
                for user_id in task_plan_rows.scalars().all()
                if str(user_id or "").strip()
            }
        finally:
            task_plan_rows.close()

    return sorted(active_user_ids | task_plan_user_ids)


async def delete_legacy_queue(
    connection: aio_pika.abc.AbstractRobustConnection,
    queue_name: str,
    dry_run: bool,
) -> tuple[str, bool, str]:
    channel = await connection.channel()
    try:
        if dry_run:
            return queue_name, False, "dry-run"

        await channel.queue_delete(queue_name, if_unused=False, if_empty=False)
        return queue_name, True, "deleted"
    except Exception as exc:
        message = str(exc)
        normalized = message.lower()
        if "not_found" in normalized or "not found" in normalized or "404" in normalized:
            return queue_name, False, "not-found"
        raise
    finally:
        try:
            await channel.close()
        except Exception:
            pass


async def main() -> int:
    parser = argparse.ArgumentParser(description="清理 legacy seller.rpa.user.inbox.* RabbitMQ 队列")
    parser.add_argument("--user-id", action="append", help="只删除指定 user_id 的旧队列，可重复传入")
    parser.add_argument("--dry-run", action="store_true", help="仅打印待删除队列，不执行实际删除")
    args = parser.parse_args()

    settings = SettingsFactory.initialize(
        settings_class=Settings,
        config_dir=Path(__file__).resolve().parents[1] / "configs",
    )
    DatabaseManager.initialize(settings.mysql)

    user_ids = await collect_target_user_ids(args.user_id)
    if not user_ids:
        LOGGER.info("未找到任何待清理的 user_id")
        await DatabaseManager.close()
        return 0

    LOGGER.info("开始清理 legacy seller inbox 队列", dry_run=args.dry_run, user_count=len(user_ids))

    connection = await aio_pika.connect_robust(
        host=settings.rabbitmq_web_stomp.host,
        port=settings.rabbitmq_web_stomp.port,
        login=settings.rabbitmq_web_stomp.username,
        password=settings.rabbitmq_web_stomp.password,
        virtualhost=settings.rabbitmq_web_stomp.vhost,
    )

    deleted_count = 0
    not_found_count = 0
    try:
        for user_id in user_ids:
            queue_name = f"{LEGACY_QUEUE_PREFIX}.{user_id}"
            queue_name, deleted, status = await delete_legacy_queue(
                connection=connection,
                queue_name=queue_name,
                dry_run=args.dry_run,
            )
            if deleted:
                deleted_count += 1
            elif status == "not-found":
                not_found_count += 1

            LOGGER.info(
                "legacy seller inbox 队列处理结果",
                queue_name=queue_name,
                status=status,
            )
    finally:
        await connection.close()
        await DatabaseManager.close()

    LOGGER.info(
        "legacy seller inbox 队列清理完成",
        dry_run=args.dry_run,
        user_count=len(user_ids),
        deleted_count=deleted_count,
        not_found_count=not_found_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
