from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple
from uuid import uuid4

import aio_pika
from aio_pika import Message
from aio_pika.abc import (
    AbstractRobustChannel,
    AbstractRobustConnection,
    AbstractRobustExchange,
)

from apps.portal_seller_open_api.core.config import IFRabbitMQWebSTOMPSettings
from core_base import get_logger


class RabbitMQProducer:
    _logger = get_logger("SellerUserNotificationProducer")
    _settings: Optional[IFRabbitMQWebSTOMPSettings] = None
    _connection: Optional[AbstractRobustConnection] = None
    _channel: Optional[AbstractRobustChannel] = None
    _exchange: Optional[AbstractRobustExchange] = None
    _initialized: bool = False
    _declared_queues: set[str] = set()

    USER_NOTIFICATION_QUEUE_PREFIX = "user.notification"
    USER_NOTIFICATION_MAX_LENGTH = 1000
    USER_NOTIFICATION_QUEUE_TTL_MS = 7 * 24 * 60 * 60 * 1000
    DEFAULT_MESSAGE_TTL_MS = 6 * 60 * 60 * 1000
    EVENT_NEW_TASK_READY = "NEW_TASK_READY"
    EVENT_CANCEL_TASK = "CANCEL_TASK"

    @classmethod
    async def initialize(cls, settings: IFRabbitMQWebSTOMPSettings) -> None:
        if cls._initialized and cls._connection and cls._exchange:
            return

        if not settings.host or not settings.exchange_name:
            cls._logger.warning(
                "RabbitMQ Web STOMP 配置不完整，跳过 seller producer 初始化",
                host=settings.host,
                exchange=settings.exchange_name,
            )
            return

        cls._settings = settings
        cls._connection = await aio_pika.connect_robust(
            host=settings.host,
            port=settings.port,
            login=settings.username,
            password=settings.password,
            virtualhost=settings.vhost,
        )
        cls._channel = await cls._connection.channel()
        cls._exchange = await cls._channel.declare_exchange(
            settings.exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        cls._initialized = True
        cls._logger.info(
            "Seller user.notification producer 初始化成功",
            exchange=settings.exchange_name,
        )

    @classmethod
    async def close(cls) -> None:
        if cls._connection and not cls._connection.is_closed:
            await cls._connection.close()
        cls._connection = None
        cls._channel = None
        cls._exchange = None
        cls._settings = None
        cls._initialized = False
        cls._declared_queues.clear()

    @classmethod
    def is_initialized(cls) -> bool:
        return bool(cls._initialized and cls._connection and cls._exchange)

    @classmethod
    async def _get_exchange(cls) -> AbstractRobustExchange:
        if not cls._exchange:
            raise RuntimeError("RabbitMQProducer is not initialized")
        return cls._exchange

    @classmethod
    async def _get_channel(cls) -> AbstractRobustChannel:
        if not cls._channel:
            raise RuntimeError("RabbitMQProducer channel is not initialized")
        return cls._channel

    @classmethod
    def build_user_notification_binding(cls, user_id: str) -> Tuple[str, str, str]:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id is required for user notification queue")

        queue_name = f"{cls.USER_NOTIFICATION_QUEUE_PREFIX}.{normalized_user_id}"
        routing_key = f"{cls.USER_NOTIFICATION_QUEUE_PREFIX}.{normalized_user_id}"
        return queue_name, routing_key, routing_key

    @classmethod
    async def _try_reuse_existing_queue(
        cls,
        *,
        queue_name: str,
        binding_key: str,
    ) -> bool:
        if not cls._connection or not cls._settings:
            return False

        check_channel: AbstractRobustChannel | None = None
        try:
            # Use a separate channel for passive lookup so an absent queue
            # won't poison the main producer channel.
            check_channel = await cls._connection.channel()
            queue = await check_channel.get_queue(queue_name, ensure=True)
            await queue.bind(cls._settings.exchange_name, routing_key=binding_key)
            cls._logger.info(
                "复用已存在的用户通知队列",
                queue_name=queue_name,
                binding_key=binding_key,
            )
            return True
        except Exception as exc:
            cls._logger.debug(
                "用户通知队列不存在或无法直接复用，准备按当前配置创建",
                queue_name=queue_name,
                binding_key=binding_key,
                error=str(exc),
            )
            return False
        finally:
            if check_channel is not None:
                try:
                    await check_channel.close()
                except Exception:
                    pass

    @classmethod
    async def ensure_user_notification_queue(cls, user_id: str) -> Tuple[str, str, str]:
        channel = await cls._get_channel()
        exchange = await cls._get_exchange()
        queue_name, binding_key, publish_routing_key = cls.build_user_notification_binding(
            user_id
        )

        if queue_name not in cls._declared_queues:
            reused = await cls._try_reuse_existing_queue(
                queue_name=queue_name,
                binding_key=binding_key,
            )
            if not reused:
                queue = await channel.declare_queue(
                    queue_name,
                    durable=True,
                    auto_delete=False,
                    arguments={
                        "x-message-ttl": cls.USER_NOTIFICATION_QUEUE_TTL_MS,
                        "x-max-length": cls.USER_NOTIFICATION_MAX_LENGTH,
                    },
                )
                await queue.bind(exchange, routing_key=binding_key)
                cls._logger.info(
                    "用户通知队列已声明并绑定",
                    queue_name=queue_name,
                    binding_key=binding_key,
                    queue_ttl_ms=cls.USER_NOTIFICATION_QUEUE_TTL_MS,
                    max_length=cls.USER_NOTIFICATION_MAX_LENGTH,
                )
            cls._declared_queues.add(queue_name)

        return queue_name, binding_key, publish_routing_key

    @classmethod
    async def publish_user_task_message(
        cls,
        *,
        user_id: str,
        task_id: str,
        task_type: str,
        scheduled_time: datetime,
        payload: dict[str, Any] | None = None,
        message_ttl_ms: Optional[int] = None,
    ) -> dict[str, Any]:
        ttl_ms = int(message_ttl_ms or cls.DEFAULT_MESSAGE_TTL_MS)
        queue_name, binding_key, publish_routing_key = (
            await cls.ensure_user_notification_queue(user_id=user_id)
        )
        exchange = await cls._get_exchange()

        message_id = str(uuid4()).upper()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(milliseconds=max(ttl_ms, 0))
        task_name = str((payload or {}).get("taskName") or "").strip()
        message_body = {
            "eventType": cls.EVENT_NEW_TASK_READY,
            "title": cls.EVENT_NEW_TASK_READY,
            "type": "notification",
            "payloadVersion": "2026-03-26",
            "messageId": message_id,
            "userId": user_id,
            "taskId": task_id,
            "taskType": task_type,
            "scheduledTime": _to_utc_iso(scheduled_time),
            "expiresAt": _to_utc_iso(expires_at),
        }
        if task_name:
            message_body["content"] = f"任务《{task_name}》已立即执行"
        if payload:
            message_body["payload"] = payload

        message = Message(
            json.dumps(message_body, ensure_ascii=False, default=str).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
            message_id=message_id,
            expiration=_build_message_expiration(ttl_ms),
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
        await exchange.publish(message, routing_key=publish_routing_key)
        cls._logger.info(
            "Seller RPA 任务消息已发送到用户通知队列",
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

        ttl_ms = int(message_ttl_ms or cls.DEFAULT_MESSAGE_TTL_MS)
        queue_name, binding_key, publish_routing_key = (
            await cls.ensure_user_notification_queue(user_id=user_id)
        )
        exchange = await cls._get_exchange()

        message_id = str(uuid4()).upper()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(milliseconds=max(ttl_ms, 0))
        task_name = str((payload or {}).get("taskName") or "").strip()
        message_body: dict[str, Any] = {
            "eventType": normalized_event_type,
            "title": normalized_event_type,
            "type": "notification",
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
        if task_name:
            event_content = (
                f"任务《{task_name}》已取消"
                if normalized_event_type == cls.EVENT_CANCEL_TASK
                else f"任务《{task_name}》事件已触发"
            )
            message_body["content"] = event_content
        if payload:
            message_body["payload"] = payload

        message = Message(
            json.dumps(message_body, ensure_ascii=False, default=str).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
            message_id=message_id,
            expiration=_build_message_expiration(ttl_ms),
            headers={
                "event_type": normalized_event_type,
                "task_id": str(task_id or "").strip(),
                "task_type": str(task_type or "").strip().upper(),
                "user_id": str(user_id).strip(),
                "queue_name": queue_name,
                "binding_key": binding_key,
            },
        )
        await exchange.publish(message, routing_key=publish_routing_key)
        cls._logger.info(
            "Seller RPA 事件消息已发送到用户通知队列",
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

    @classmethod
    async def publish_user_notification_message(
        cls,
        *,
        user_id: str,
        title: str,
        content: str,
        message_type: str = "notification",
        extra_data: dict[str, Any] | None = None,
        message_ttl_ms: Optional[int] = None,
    ) -> dict[str, Any]:
        ttl_ms = int(message_ttl_ms or cls.USER_NOTIFICATION_QUEUE_TTL_MS)
        queue_name, binding_key, publish_routing_key = (
            await cls.ensure_user_notification_queue(user_id=user_id)
        )
        exchange = await cls._get_exchange()

        message_id = f"msg-{uuid4()}"
        timestamp = datetime.now(timezone.utc)
        message_body = {
            "messages": [
                {
                    "id": message_id,
                    "title": str(title).strip(),
                    "content": str(content).strip(),
                    "type": str(message_type or "notification").strip() or "notification",
                    "timestamp": timestamp.isoformat(),
                    "userId": str(user_id).strip(),
                    **(extra_data or {}),
                }
            ]
        }

        message = Message(
            json.dumps(message_body, ensure_ascii=False, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            expiration=_build_message_expiration(ttl_ms),
            message_id=message_id,
            headers={
                "message_type": str(message_type or "notification").strip() or "notification",
                "user_id": str(user_id).strip(),
                "queue_name": queue_name,
                "binding_key": binding_key,
            },
        )
        await exchange.publish(message, routing_key=publish_routing_key)
        cls._logger.info(
            "通用用户通知消息已发送到用户通知队列",
            queue_name=queue_name,
            routing_key=publish_routing_key,
            message_id=message_id,
            user_id=user_id,
        )
        return {
            "message_id": message_id,
            "queue_name": queue_name,
            "binding_key": binding_key,
            "routing_key": publish_routing_key,
            "message_ttl_ms": ttl_ms,
            "published_at": timestamp.isoformat(),
        }


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_message_expiration(ttl_ms: int) -> timedelta | None:
    normalized_ttl_ms = int(ttl_ms or 0)
    if normalized_ttl_ms <= 0:
        return None
    return timedelta(milliseconds=normalized_ttl_ms)
