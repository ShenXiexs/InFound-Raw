from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from apps.portal_seller_open_api.core.config import Settings
from core_base import get_logger
from core_redis import RedisClientManager
from shared_domain.models.infound import SellerTkRpaTaskPlans


@dataclass(frozen=True)
class TaskDispatchResult:
    published: bool
    message_id: str | None = None
    reason: str | None = None


class SellerRpaTaskDispatchService:
    SUPPORTED_DELAYED_TASK_TYPES = {
        "OUTREACH",
        "CREATOR_DETAIL",
        "CHAT",
        "SAMPLE_MONITOR",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = get_logger(self.__class__.__name__)
        self.redis_prefix = str(self.settings.redis.prefix or "seller").rstrip(":")
        self.dispatch_marker_ttl_seconds = max(
            int(self.settings.seller_rpa_scheduler.dispatch_marker_ttl_seconds or 21600),
            60,
        )

    async def schedule_task_plan(self, task_plan: SellerTkRpaTaskPlans) -> bool:
        task_type = str(task_plan.task_type or "").upper()
        if task_type not in self.SUPPORTED_DELAYED_TASK_TYPES:
            return False
        key = self._delayed_zset_key(task_type)
        score = self._to_epoch_seconds(task_plan.scheduled_time)
        client = RedisClientManager.get_client()
        await asyncio.to_thread(client.zadd, key, {task_plan.id: score})
        return True

    async def try_publish_task_plan(
        self, task_plan: SellerTkRpaTaskPlans
    ) -> TaskDispatchResult:
        if task_plan.status != "PENDING":
            return TaskDispatchResult(
                published=False,
                reason=f"task-status-{task_plan.status.lower()}",
            )

        marker_key = self.dispatch_marker_key(task_plan.id)
        client = RedisClientManager.get_client()
        acquired = await asyncio.to_thread(
            client.set,
            marker_key,
            datetime.utcnow().isoformat(),
            ex=self.dispatch_marker_ttl_seconds,
            nx=True,
        )
        if not acquired:
            return TaskDispatchResult(published=False, reason="already-activated")

        normalized_task_type = str(task_plan.task_type or "").upper()
        if normalized_task_type in self.SUPPORTED_DELAYED_TASK_TYPES:
            await asyncio.to_thread(
                client.zrem,
                self._delayed_zset_key(normalized_task_type),
                task_plan.id,
            )
        return TaskDispatchResult(
            published=True,
            reason="activated",
        )

    async def clear_task_plan(self, task_id: str, task_type: str | None) -> None:
        client = RedisClientManager.get_client()
        actions = [asyncio.to_thread(client.delete, self.dispatch_marker_key(task_id))]
        normalized_task_type = str(task_type or "").upper()
        if normalized_task_type in self.SUPPORTED_DELAYED_TASK_TYPES:
            actions.append(
                asyncio.to_thread(
                    client.zrem,
                    self._delayed_zset_key(normalized_task_type),
                    task_id,
                )
            )
        await asyncio.gather(*actions, return_exceptions=True)

    async def get_due_task_ids(
        self,
        task_type: str,
        *,
        now: datetime | None = None,
        batch_size: int = 50,
    ) -> list[str]:
        normalized_task_type = str(task_type or "").upper()
        if normalized_task_type not in self.SUPPORTED_DELAYED_TASK_TYPES:
            return []
        client = RedisClientManager.get_client()
        max_score = self._to_epoch_seconds(now or datetime.utcnow())
        members = await asyncio.to_thread(
            client.zrangebyscore,
            self._delayed_zset_key(normalized_task_type),
            "-inf",
            max_score,
            0,
            max(int(batch_size), 1),
        )
        return [str(item) for item in members]

    async def has_dispatch_marker(self, task_id: str) -> bool:
        client = RedisClientManager.get_client()
        return bool(await asyncio.to_thread(client.exists, self.dispatch_marker_key(task_id)))

    def delayed_zset_key(self, task_type: str) -> str:
        return self._delayed_zset_key(task_type)

    def dispatch_marker_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}:seller_rpa:dispatch:{task_id}"

    def _delayed_zset_key(self, task_type: str) -> str:
        return f"{self.redis_prefix}:seller_rpa:delayed:{str(task_type or '').upper()}"

    @staticmethod
    def _to_epoch_seconds(value: datetime) -> int:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())
