from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple
from uuid import uuid4

import aio_pika
from aio_pika import Message

from core_base import get_logger
from core_mq import RabbitMQConnection
from core_mq.rabbitmq_setting import QueueConfig, RabbitMQSettings


class RabbitMQProducer:
    _logger = get_logger("SellerRabbitMQProducer")
    _settings: Optional[RabbitMQSettings] = None
    _connection: Optional[RabbitMQConnection] = None
    _initialized: bool = False

    INBOX_QUEUE_KEY = "seller_rpa_inbox"
    DEFAULT_MESSAGE_TTL_MS = 6 * 60 * 60 * 1000
    EVENT_NEW_TASK_READY = "NEW_TASK_READY"
    EVENT_CANCEL_TASK = "CANCEL_TASK"

    @classmethod
    async def initialize(cls, settings: RabbitMQSettings) -> None:
        if cls._initialized and cls._connection and cls._connection.exchange:
            return

        if not settings.host or not settings.exchange_name:
            cls._logger.warning(
                "RabbitMQ 配置不完整，跳过 seller producer 初始化",
                host=settings.host,
                exchange=settings.exchange_name,
            )
            return

        cls._settings = settings
        cls._connection = RabbitMQConnection(
            url=settings.url,
            exchange_name=settings.exchange_name,
            exchange_type=aio_pika.ExchangeType.TOPIC,
            prefetch_count=settings.prefetch_count or 10,
            reconnect_delay=settings.reconnect_delay,
            max_reconnect_attempts=settings.max_reconnect_attempts,
        )
        await cls._connection.connect()
        cls._initialized = True
        cls._logger.info(
            "Seller RabbitMQ producer 初始化成功",
            exchange=settings.exchange_name,
        )

    @classmethod
    async def close(cls) -> None:
        if cls._connection:
            await cls._connection.close()
        cls._connection = None
        cls._settings = None
        cls._initialized = False

    @classmethod
    def is_initialized(cls) -> bool:
        return bool(cls._initialized and cls._connection and cls._connection.exchange)

    @classmethod
    async def _get_connection(cls) -> RabbitMQConnection:
        if not cls._connection:
            raise RuntimeError("RabbitMQProducer is not initialized")
        return cls._connection

    @classmethod
    def _get_inbox_queue_setting(cls) -> QueueConfig:
        if not cls._settings:
            raise RuntimeError("RabbitMQProducer settings are not initialized")
        queue_setting = cls._settings.queues.get(cls.INBOX_QUEUE_KEY)
        if queue_setting is None:
            raise RuntimeError(f"RabbitMQ queue config '{cls.INBOX_QUEUE_KEY}' is missing")
        return queue_setting

    @classmethod
    def build_user_inbox_binding(
        cls,
        user_id: str,
        *,
        event_suffix: str = "task.ready",
    ) -> Tuple[str, str, str]:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id is required for seller inbox queue")

        queue_setting = cls._get_inbox_queue_setting()
        queue_prefix = str(queue_setting.queue_prefix or queue_setting.queue_name or "").strip(".")
        routing_prefix = str(queue_setting.routing_key_pattern or "").strip()
        routing_prefix = routing_prefix.rstrip(".*").rstrip(".")
        if not queue_prefix or not routing_prefix:
            raise RuntimeError("Seller inbox queue prefix settings are required")

        queue_name = f"{queue_prefix}.{normalized_user_id}"
        binding_key = f"{routing_prefix}.{normalized_user_id}.*"
        normalized_event_suffix = str(event_suffix or "task.ready").strip().strip(".")
        publish_routing_key = f"{routing_prefix}.{normalized_user_id}.{normalized_event_suffix}"
        return queue_name, binding_key, publish_routing_key

    @classmethod
    async def ensure_user_inbox(
        cls,
        user_id: str,
        *,
        message_ttl_ms: Optional[int] = None,
        event_suffix: str = "task.ready",
    ) -> Tuple[str, str, str]:
        conn = await cls._get_connection()
        queue_setting = cls._get_inbox_queue_setting()
        queue_name, binding_key, publish_routing_key = cls.build_user_inbox_binding(
            user_id,
            event_suffix=event_suffix,
        )

        if queue_name not in conn.queues:
            queue_arguments: dict[str, Any] = {}
            ttl_ms = int(message_ttl_ms or cls.DEFAULT_MESSAGE_TTL_MS)
            if ttl_ms > 0:
                queue_arguments["x-message-ttl"] = ttl_ms

            await conn.add_queue(
                queue_name=queue_name,
                routing_key=binding_key,
                durable=queue_setting.durable,
                auto_delete=queue_setting.auto_delete,
                exclusive=queue_setting.exclusive,
                arguments=queue_arguments or None,
            )
            cls._logger.info(
                "Seller 用户收件箱已创建",
                queue_name=queue_name,
                binding_key=binding_key,
                message_ttl_ms=ttl_ms,
            )

        return queue_name, binding_key, publish_routing_key

    @classmethod
    async def publish_user_task_message(
        cls,
        *,
        user_id: str,
        task_id: str,
        task_type: str,
        scheduled_time: datetime,
        payload: dict[str, Any],
        message_ttl_ms: Optional[int] = None,
    ) -> dict[str, Any]:
        ttl_ms = int(message_ttl_ms or cls.DEFAULT_MESSAGE_TTL_MS)
        queue_name, binding_key, publish_routing_key = await cls.ensure_user_inbox(
            user_id=user_id,
            message_ttl_ms=ttl_ms,
            event_suffix="task.ready",
        )
        conn = await cls._get_connection()
        if not conn.exchange:
            raise RuntimeError("RabbitMQ exchange is not initialized")

        message_id = str(uuid4()).upper()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(milliseconds=max(ttl_ms, 0))
        message_body = {
            "eventType": cls.EVENT_NEW_TASK_READY,
            "payloadVersion": "2026-03-26",
            "messageId": message_id,
            "userId": user_id,
            "taskId": task_id,
            "taskType": task_type,
            "scheduledTime": _to_utc_iso(scheduled_time),
            "expiresAt": _to_utc_iso(expires_at),
            "payload": payload,
        }

        message = Message(
            json.dumps(message_body, ensure_ascii=False, default=str).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
            message_id=message_id,
            expiration=str(ttl_ms),
            headers={
                "event_type": cls.EVENT_NEW_TASK_READY,
                "task_id": task_id,
                "task_type": task_type,
                "user_id": user_id,
                "queue_name": queue_name,
                "binding_key": binding_key,
                "payload_version": "2026-03-26",
            },
        )
        await conn.exchange.publish(message, routing_key=publish_routing_key)
        cls._logger.info(
            "Seller RPA 任务消息已发送到用户收件箱",
            queue_name=queue_name,
            routing_key=publish_routing_key,
            task_id=task_id,
            user_id=user_id,
        )
        return {
            "message_id": message_id,
            "queue_name": queue_name,
            "binding_key": binding_key,
            "routing_key": publish_routing_key,
            "message_ttl_ms": ttl_ms,
            "expires_at": _to_utc_iso(expires_at),
        }

    @classmethod
    async def publish_user_event_message(
        cls,
        *,
        event_type: str,
        user_id: str,
        task_id: str | None = None,
        task_type: str | None = None,
        payload: dict[str, Any] | None = None,
        scheduled_time: datetime | None = None,
        message_ttl_ms: Optional[int] = None,
    ) -> dict[str, Any]:
        normalized_event_type = str(event_type or "").strip().upper()
        if not normalized_event_type:
            raise ValueError("event_type is required")

        event_suffix = {
            cls.EVENT_NEW_TASK_READY: "task.ready",
            cls.EVENT_CANCEL_TASK: "task.cancel",
        }.get(normalized_event_type, normalized_event_type.lower().replace("_", "."))

        ttl_ms = int(message_ttl_ms or cls.DEFAULT_MESSAGE_TTL_MS)
        queue_name, binding_key, publish_routing_key = await cls.ensure_user_inbox(
            user_id=user_id,
            message_ttl_ms=ttl_ms,
            event_suffix=event_suffix,
        )
        conn = await cls._get_connection()
        if not conn.exchange:
            raise RuntimeError("RabbitMQ exchange is not initialized")

        message_id = str(uuid4()).upper()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(milliseconds=max(ttl_ms, 0))
        message_body: dict[str, Any] = {
            "eventType": normalized_event_type,
            "messageId": message_id,
            "userId": str(user_id).strip(),
            "activatedAt": _to_utc_iso(now),
            "expiresAt": _to_utc_iso(expires_at),
        }
        if task_id:
            message_body["taskId"] = str(task_id).strip()
        if task_type:
            message_body["taskType"] = str(task_type).strip().upper()
        if scheduled_time is not None:
            message_body["scheduledTime"] = _to_utc_iso(scheduled_time)
        if payload:
            message_body["payload"] = payload

        message = Message(
            json.dumps(message_body, ensure_ascii=False, default=str).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
            message_id=message_id,
            headers={
                "event_type": normalized_event_type,
                "task_id": str(task_id or "").strip(),
                "task_type": str(task_type or "").strip().upper(),
                "user_id": str(user_id).strip(),
                "queue_name": queue_name,
                "binding_key": binding_key,
            },
        )
        await conn.exchange.publish(message, routing_key=publish_routing_key)
        cls._logger.info(
            "Seller RPA 事件消息已发送到用户收件箱",
            event_type=normalized_event_type,
            queue_name=queue_name,
            routing_key=publish_routing_key,
            task_id=task_id,
            user_id=user_id,
        )
        return {
            "message_id": message_id,
            "queue_name": queue_name,
            "binding_key": binding_key,
            "routing_key": publish_routing_key,
            "message_ttl_ms": ttl_ms,
            "expires_at": _to_utc_iso(expires_at),
        }


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
