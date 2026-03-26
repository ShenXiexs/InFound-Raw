from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.core.rabbitmq_producer import RabbitMQProducer
from core_base import get_logger
from shared_domain.models.infound import SellerTkRpaTaskPlans


@dataclass(frozen=True)
class SellerRpaTaskNotificationResult:
    notified: bool
    event_type: str
    message_id: str | None = None
    queue_name: str | None = None
    routing_key: str | None = None
    reason: str | None = None


class SellerRpaTaskNotificationService:
    EVENT_NEW_TASK_READY = RabbitMQProducer.EVENT_NEW_TASK_READY
    EVENT_CANCEL_TASK = RabbitMQProducer.EVENT_CANCEL_TASK

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = get_logger(self.__class__.__name__)

    async def notify_task_ready(
        self,
        task_plan: SellerTkRpaTaskPlans,
        *,
        payload: dict[str, Any] | None = None,
    ) -> SellerRpaTaskNotificationResult:
        normalized_user_id = str(task_plan.user_id or "").strip()
        if not normalized_user_id:
            return SellerRpaTaskNotificationResult(
                notified=False,
                event_type=self.EVENT_NEW_TASK_READY,
                reason="missing-user-id",
            )

        try:
            if not RabbitMQProducer.is_initialized():
                await RabbitMQProducer.initialize(self.settings.rabbitmq)

            publish_result = await RabbitMQProducer.publish_user_task_message(
                user_id=normalized_user_id,
                task_id=str(task_plan.id or "").strip(),
                task_type=str(task_plan.task_type or "").strip().upper(),
                scheduled_time=task_plan.scheduled_time,
                payload=self._build_task_message_payload(task_plan, payload or {}),
            )
            return SellerRpaTaskNotificationResult(
                notified=True,
                event_type=self.EVENT_NEW_TASK_READY,
                message_id=str(publish_result.get("message_id") or "").strip() or None,
                queue_name=str(publish_result.get("queue_name") or "").strip() or None,
                routing_key=str(publish_result.get("routing_key") or "").strip() or None,
            )
        except Exception as exc:
            self.logger.error(
                "Seller RPA 完整任务消息发送失败",
                task_id=task_plan.id,
                task_type=task_plan.task_type,
                user_id=normalized_user_id,
                error=str(exc),
                exc_info=True,
            )
            return SellerRpaTaskNotificationResult(
                notified=False,
                event_type=self.EVENT_NEW_TASK_READY,
                reason=str(exc),
            )

    async def notify_task_cancelled(
        self,
        task_plan: SellerTkRpaTaskPlans,
        *,
        payload: dict[str, Any] | None = None,
    ) -> SellerRpaTaskNotificationResult:
        return await self._publish_task_event(
            event_type=self.EVENT_CANCEL_TASK,
            task_plan=task_plan,
            payload=payload or {},
        )

    async def _publish_task_event(
        self,
        *,
        event_type: str,
        task_plan: SellerTkRpaTaskPlans,
        payload: dict[str, Any],
    ) -> SellerRpaTaskNotificationResult:
        normalized_user_id = str(task_plan.user_id or "").strip()
        if not normalized_user_id:
            return SellerRpaTaskNotificationResult(
                notified=False,
                event_type=event_type,
                reason="missing-user-id",
            )

        try:
            if not RabbitMQProducer.is_initialized():
                await RabbitMQProducer.initialize(self.settings.rabbitmq)

            publish_result = await RabbitMQProducer.publish_user_event_message(
                event_type=event_type,
                user_id=normalized_user_id,
                task_id=str(task_plan.id or "").strip() or None,
                task_type=str(task_plan.task_type or "").strip() or None,
                scheduled_time=task_plan.scheduled_time,
                payload=payload,
            )
            return SellerRpaTaskNotificationResult(
                notified=True,
                event_type=event_type,
                message_id=str(publish_result.get("message_id") or "").strip() or None,
                queue_name=str(publish_result.get("queue_name") or "").strip() or None,
                routing_key=str(publish_result.get("routing_key") or "").strip() or None,
            )
        except Exception as exc:
            self.logger.error(
                "Seller RPA 事件通知发送失败",
                event_type=event_type,
                task_id=task_plan.id,
                task_type=task_plan.task_type,
                user_id=normalized_user_id,
                error=str(exc),
                exc_info=True,
            )
            return SellerRpaTaskNotificationResult(
                notified=False,
                event_type=event_type,
                reason=str(exc),
            )

    def _build_task_message_payload(
        self,
        task_plan: SellerTkRpaTaskPlans,
        override_payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._coerce_payload(task_plan.task_payload)
        if override_payload:
            payload.update(override_payload)

        task_node = self._ensure_record(payload.get("task"))
        input_node = self._ensure_record(payload.get("input"))
        executor_node = self._ensure_record(payload.get("executor"))
        input_payload_node = self._ensure_record(input_node.get("payload"))
        input_report_node = self._ensure_record(input_node.get("report"))

        if not task_node:
            payload["task"] = task_node
        if not input_node:
            payload["input"] = input_node
        if not executor_node:
            payload["executor"] = executor_node
        if not input_payload_node:
            input_node["payload"] = input_payload_node

        task_node.setdefault("taskId", str(task_plan.id or "").strip())
        task_node.setdefault("taskType", str(task_plan.task_type or "").strip().upper())
        task_node.setdefault("taskStatus", str(task_plan.status or "").strip().upper())
        task_node.setdefault("scheduledTime", task_plan.scheduled_time.isoformat())
        if task_plan.creation_time is not None:
            task_node.setdefault("createdAt", task_plan.creation_time.isoformat())
        if task_plan.last_modification_time is not None:
            task_node.setdefault(
                "updatedAt", task_plan.last_modification_time.isoformat()
            )

        if task_plan.shop_id:
            task_node.setdefault("shopId", str(task_plan.shop_id).strip())
            input_payload_node.setdefault("shopId", str(task_plan.shop_id).strip())
        if task_plan.shop_region_code:
            task_node.setdefault(
                "shopRegionCode", str(task_plan.shop_region_code).strip().upper()
            )
            input_payload_node.setdefault(
                "shopRegionCode", str(task_plan.shop_region_code).strip().upper()
            )

        task_name = input_payload_node.get("taskName") or task_node.get("taskName")
        if not task_name:
            task_name = f"{str(task_plan.task_type or '').strip().upper()}-{str(task_plan.id or '')[:8]}"
        task_node.setdefault("taskName", task_name)
        input_payload_node.setdefault("taskId", str(task_plan.id or "").strip())
        input_payload_node.setdefault(
            "taskType", str(task_plan.task_type or "").strip().upper()
        )
        input_payload_node.setdefault("taskName", task_name)
        input_payload_node.setdefault(
            "scheduledTime", task_plan.scheduled_time.isoformat()
        )

        executor_node.setdefault("host", "frontend.desktop")
        executor_node.setdefault("dispatchMode", "user_inbox")
        executor_node.setdefault("transport", "rabbitmq_web_stomp")
        executor_node.setdefault("authMode", "jwt")

        if input_report_node:
            input_node["report"] = input_report_node

        return payload

    def _coerce_payload(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return deepcopy(value)
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return {}
            try:
                parsed = json.loads(normalized)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _ensure_record(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}
