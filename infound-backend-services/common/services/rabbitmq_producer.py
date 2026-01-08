from __future__ import annotations

import asyncio
import json
from typing import List, Optional, Dict, Any, Set, Tuple
from urllib.parse import quote_plus
from uuid import uuid4

import aio_pika
from aio_pika import Channel, Exchange, Message
from aio_pika.abc import AbstractConnection

from common.core.config import get_settings
from common.core.logger import get_logger

settings = get_settings()
logger = get_logger()


class RabbitMQProducer:
    """
    RabbitMQ 消息生产者，用于批量发送聊天机器人消息。
    """

    _connection: Optional[AbstractConnection] = None
    _channel: Optional[Channel] = None
    _exchange: Optional[Exchange] = None
    _crawler_exchange: Optional[Exchange] = None
    _dlx_exchange: Optional[Exchange] = None
    _initialized: bool = False
    _bindings: Set[Tuple[str, str]] = set()
    _bind_lock = asyncio.Lock()

    @classmethod
    async def initialize(cls) -> None:
        """初始化 RabbitMQ 连接、通道和交换机"""
        if cls._initialized and cls._connection and not cls._connection.is_closed:
            return

        try:
            if not settings.RABBITMQ_HOST or not settings.RABBITMQ_EXCHANGE or not settings.RABBITMQ_QUEUE:
                logger.warning(
                    "RabbitMQ 配置不完整，跳过初始化",
                    host=settings.RABBITMQ_HOST,
                    exchange=settings.RABBITMQ_EXCHANGE,
                    queue=settings.RABBITMQ_QUEUE,
                )
                return

            vhost = str(getattr(settings, "RABBITMQ_VHOST", "/") or "/")
            # vhost 在 URL path segment 中需要做完整 URL encode（比如 "/" -> "%2F"）
            vhost_path = quote_plus(vhost)
            # 构建连接 URL（注意对特殊字符做 URL encode）
            connection_url = (
                f"amqp://{quote_plus(settings.RABBITMQ_USER)}:{quote_plus(settings.RABBITMQ_PASSWORD)}"
                f"@{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/"
                f"{vhost_path}"
            )

            # 创建连接（使用 robust 连接，自动重连）
            cls._connection = await aio_pika.connect_robust(connection_url)

            # 创建通道
            cls._channel = await cls._connection.channel()

            # 声明交换机（topic 类型，支持路由键匹配）
            cls._exchange = await cls._channel.declare_exchange(
                settings.RABBITMQ_EXCHANGE,
                aio_pika.ExchangeType.TOPIC,
                durable=True  # 持久化交换机
            )

            # 默认队列绑定（sample chatbot）
            routing_key_prefix = str(getattr(settings, "RABBITMQ_ROUTING_KEY_PREFIX", "") or "").strip()
            if not routing_key_prefix:
                raise ValueError("RABBITMQ_ROUTING_KEY_PREFIX is required")
            await cls._ensure_binding(
                queue_name=settings.RABBITMQ_QUEUE,
                routing_key_prefix=routing_key_prefix,
            )

            crawler_exchange = str(
                getattr(settings, "RABBITMQ_CRAWLER_EXCHANGE", "") or ""
            ).strip()
            crawler_routing_key = str(
                getattr(settings, "RABBITMQ_CRAWLER_ROUTING_KEY", "") or ""
            ).strip()
            crawler_queue = str(
                getattr(settings, "RABBITMQ_CRAWLER_QUEUE", "") or ""
            ).strip()
            if crawler_exchange:
                cls._crawler_exchange = await cls._channel.declare_exchange(
                    crawler_exchange,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True,
                )
                if crawler_queue and crawler_routing_key:
                    crawler_dlx_name = f"{crawler_exchange}.dlx"
                    crawler_dlx_routing_key = f"{crawler_routing_key}.dead"
                    queue = await cls._channel.declare_queue(
                        crawler_queue,
                        durable=True,
                        arguments={
                            "x-dead-letter-exchange": crawler_dlx_name,
                            "x-dead-letter-routing-key": crawler_dlx_routing_key,
                        },
                    )
                    await queue.bind(cls._crawler_exchange, routing_key=crawler_routing_key)

            cls._initialized = True
            logger.info(
                "RabbitMQ 生产者初始化成功",
                host=settings.RABBITMQ_HOST,
                exchange=settings.RABBITMQ_EXCHANGE,
                queue=settings.RABBITMQ_QUEUE
            )
        except Exception as e:
            logger.error(
                "RabbitMQ 生产者初始化失败",
                error=str(e),
                exc_info=True
            )
            cls._connection = None
            cls._channel = None
            cls._exchange = None
            cls._crawler_exchange = None
            cls._initialized = False
            # 不抛出异常，允许服务继续运行（MQ 为可选功能）

    @classmethod
    async def publish_batch_chatbot_messages(
        cls,
        tasks: List[Dict[str, Any]],
        *,
        routing_key_prefix: Optional[str] = None,
        queue_name: Optional[str] = None,
        binding_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        批量发布聊天机器人消息到 RabbitMQ（每条任务单独入队）。

        Args:
            tasks: 任务列表，每个任务包含：
                - region: 地区
                - platformCreatorId: 平台创作者ID
                - messages: [{type, content, meta?}, ...]
        """
        if not cls._initialized or cls._exchange is None:
            raise RuntimeError("RabbitMQProducer is not initialized")

        if not tasks:
            return

        prefix = str(
            routing_key_prefix
            or getattr(settings, "RABBITMQ_ROUTING_KEY_PREFIX", "")
            or ""
        ).strip()
        if not prefix:
            raise ValueError("routing_key_prefix is required")
        queue_name = queue_name or settings.RABBITMQ_QUEUE
        binding_options = dict(binding_options or {})
        await cls._ensure_binding(
            queue_name=queue_name,
            routing_key_prefix=prefix,
            **binding_options,
        )
        routing_key = f"{prefix}.batch"
        sent_count = 0
        try:
            for task in tasks:
                # 生成消息ID（仅用于 header 追踪；消息体为单条任务）
                task_id = str(uuid4()).upper()
                message_body = [task]

                # 序列化为 JSON
                message_json = json.dumps(message_body, ensure_ascii=False, default=str)

                # 创建消息（持久化）
                message = Message(
                    message_json.encode("utf-8"),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    headers={
                        "task_id": task_id,
                        "task_count": 1,
                    },
                )

                # 发布消息
                await cls._exchange.publish(message, routing_key=routing_key)
                sent_count += 1

            logger.info(
                "聊天机器人消息已发送到 RabbitMQ",
                message_count=sent_count,
                routing_key=routing_key,
            )
        except Exception as e:
            logger.error(
                "发送聊天机器人消息到 RabbitMQ 失败",
                message_count=sent_count,
                task_count=len(tasks),
                error=str(e),
                exc_info=True,
            )
            # 需要抛出异常：调度器会据此决定是否推进 schedule（避免丢任务）
            raise

    @classmethod
    async def publish_batch_outreach_chatbot_messages(
        cls,
        tasks: List[Dict[str, Any]],
    ) -> None:
        """发布建联聊天机器人消息到 RabbitMQ（使用独立 routing key）。"""
        if not tasks:
            return

        per_task_groups: Dict[Optional[str], List[Dict[str, Any]]] = {}
        for task in tasks:
            if not isinstance(task, dict):
                continue
            outreach_task_id = str(
                task.get("outreach_task_id")
                or task.get("outreachTaskId")
                or ""
            ).strip()
            per_task_groups.setdefault(outreach_task_id or None, []).append(task)

        for outreach_task_id, grouped in per_task_groups.items():
            if outreach_task_id:
                queue_name, routing_key_prefix = await cls.ensure_outreach_task_queue(
                    outreach_task_id
                )
                await cls.publish_batch_chatbot_messages(
                    grouped,
                    routing_key_prefix=routing_key_prefix,
                    queue_name=queue_name,
                    binding_options=_outreach_binding_options(),
                )
            else:
                routing_key_prefix = str(
                    getattr(settings, "RABBITMQ_OUTREACH_ROUTING_KEY_PREFIX", "") or ""
                ).strip()
                queue_name = getattr(settings, "RABBITMQ_OUTREACH_QUEUE", None) or None
                if not routing_key_prefix or not queue_name:
                    raise ValueError("Outreach RabbitMQ routing key prefix/queue is required")
                await cls.publish_batch_chatbot_messages(
                    grouped,
                    routing_key_prefix=routing_key_prefix,
                    queue_name=queue_name,
                )

    @classmethod
    async def publish_crawler_task(
        cls,
        task: Dict[str, Any],
    ) -> None:
        """Publish a crawler task message to RabbitMQ (direct exchange)."""
        if not task:
            return
        if not cls._initialized or cls._crawler_exchange is None:
            raise RuntimeError("RabbitMQProducer crawler exchange is not initialized")
        routing_key = str(
            getattr(settings, "RABBITMQ_CRAWLER_ROUTING_KEY", "") or ""
        ).strip()
        if not routing_key:
            raise ValueError("RABBITMQ_CRAWLER_ROUTING_KEY is required")

        message_json = json.dumps(task, ensure_ascii=False, default=str)
        message = Message(
            message_json.encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await cls._crawler_exchange.publish(message, routing_key=routing_key)

    @classmethod
    async def ensure_outreach_task_queue(cls, task_id: str) -> Tuple[str, str]:
        queue_name, routing_key_prefix = cls.build_outreach_task_binding(task_id)
        await cls._ensure_binding(
            queue_name=queue_name,
            routing_key_prefix=routing_key_prefix,
            **_outreach_binding_options(),
        )
        return queue_name, routing_key_prefix

    @classmethod
    def build_outreach_task_binding(cls, task_id: str) -> Tuple[str, str]:
        if not task_id:
            raise ValueError("task_id is required for outreach queue")

        routing_prefix = str(
            getattr(settings, "RABBITMQ_OUTREACH_ROUTING_KEY_PREFIX", "") or ""
        ).strip()
        queue_prefix = str(
            getattr(settings, "RABBITMQ_OUTREACH_QUEUE_PREFIX", "") or ""
        ).strip()
        if not routing_prefix or not queue_prefix:
            raise ValueError("Outreach queue prefix settings are required")

        routing_key_prefix = f"{routing_prefix}.{task_id}"
        queue_name = f"{queue_prefix}.{task_id}"
        return queue_name, routing_key_prefix

    @classmethod
    async def publish_outreach_control_message(
        cls,
        *,
        action: str,
        task_id: str,
        queue_name: str,
        routing_key_prefix: str,
    ) -> None:
        if not cls._initialized or cls._exchange is None:
            raise RuntimeError("RabbitMQProducer is not initialized")
        if not action or not task_id:
            raise ValueError("action and task_id are required")

        control_prefix = str(
            getattr(settings, "RABBITMQ_OUTREACH_CONTROL_ROUTING_KEY_PREFIX", "") or ""
        ).strip()
        control_queue = str(
            getattr(settings, "RABBITMQ_OUTREACH_CONTROL_QUEUE", "") or ""
        ).strip()
        if not control_prefix or not control_queue:
            raise ValueError("Outreach control queue settings are required")

        await cls._ensure_binding(
            queue_name=control_queue,
            routing_key_prefix=control_prefix,
        )
        routing_key = f"{control_prefix}.{action}"
        message_body = json.dumps(
            {
                "action": action,
                "task_id": task_id,
                "queue_name": queue_name,
                "routing_key_prefix": routing_key_prefix,
            },
            ensure_ascii=False,
        )
        message = Message(
            message_body.encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await cls._exchange.publish(message, routing_key=routing_key)

    @classmethod
    async def _ensure_binding(
        cls,
        *,
        queue_name: str,
        routing_key_prefix: str,
        queue_arguments: Optional[Dict[str, Any]] = None,
        queue_durable: bool = True,
        queue_auto_delete: bool = False,
        queue_exclusive: bool = False,
        dlq_arguments: Optional[Dict[str, Any]] = None,
        dlq_durable: bool = True,
        dlq_auto_delete: bool = False,
        cache: bool = True,
    ) -> None:
        if not cls._channel or not cls._exchange:
            raise RuntimeError("RabbitMQProducer channel not ready")

        binding_key = f"{routing_key_prefix}.*"
        binding_key_id = (queue_name, binding_key)
        async with cls._bind_lock:
            if cache and binding_key_id in cls._bindings:
                return

            # 声明 DLX（全局共用）
            if not cls._dlx_exchange:
                dlx_name = f"{settings.RABBITMQ_EXCHANGE}.dlx"
                cls._dlx_exchange = await cls._channel.declare_exchange(
                    dlx_name,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True,
                )

            dlq_name = f"{queue_name}.dead"
            dlq = await cls._channel.declare_queue(
                dlq_name,
                durable=dlq_durable,
                auto_delete=dlq_auto_delete,
                arguments=dlq_arguments or None,
            )
            dl_routing_key = f"{binding_key}.dead"
            await dlq.bind(cls._dlx_exchange, routing_key=dl_routing_key)

            # 声明主队列（带 DLX；确保与 consumer 声明参数一致）
            queue_args = dict(queue_arguments or {})
            queue_args.setdefault(
                "x-dead-letter-exchange", f"{settings.RABBITMQ_EXCHANGE}.dlx"
            )
            queue_args.setdefault("x-dead-letter-routing-key", dl_routing_key)
            queue = await cls._channel.declare_queue(
                queue_name,
                durable=queue_durable,
                auto_delete=queue_auto_delete,
                exclusive=queue_exclusive,
                arguments=queue_args or None,
            )

            # 绑定队列到交换机（topic 通配符路由键）
            await queue.bind(cls._exchange, routing_key=binding_key)
            if cache:
                cls._bindings.add(binding_key_id)

    @classmethod
    async def close(cls) -> None:
        """关闭连接"""
        if cls._channel and not cls._channel.is_closed:
            await cls._channel.close()
        if cls._connection and not cls._connection.is_closed:
            await cls._connection.close()
        cls._connection = None
        cls._channel = None
        cls._exchange = None
        cls._crawler_exchange = None
        cls._dlx_exchange = None
        cls._initialized = False
        cls._bindings = set()
        logger.info("RabbitMQ 生产者连接已关闭")


def _outreach_binding_options(*, cache: bool = True) -> Dict[str, Any]:
    expires_ms = 30 * 60 * 1000
    return {
        "queue_arguments": {"x-expires": expires_ms},
        "queue_durable": False,
        "queue_auto_delete": True,
        "queue_exclusive": False,
        "dlq_arguments": {"x-expires": expires_ms},
        "dlq_durable": False,
        "dlq_auto_delete": True,
        "cache": cache,
    }


