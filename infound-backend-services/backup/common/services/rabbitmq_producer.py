from __future__ import annotations

import asyncio
import json
from typing import List, Optional, Dict, Any, Set, Tuple
from urllib.parse import quote_plus
from uuid import uuid4

import aio_pika
from aio_pika import Message

from common.core.config import get_settings
from common.core.logger import get_logger
from common.mq.connection import RabbitMQConnection

settings = get_settings()
logger = get_logger()


class RabbitMQProducer:
    """
    RabbitMQ 消息生产者，用于批量发送聊天机器人消息。
    """

    _chat_conn: Optional[RabbitMQConnection] = None
    _crawler_conn: Optional[RabbitMQConnection] = None
    _initialized: bool = False
    _bindings: Set[Tuple[str, str]] = set()
    _bind_lock = asyncio.Lock()

    @classmethod
    async def initialize(cls) -> None:
        """初始化 RabbitMQ 连接、通道和交换机"""
        if (
                cls._initialized
                and cls._chat_conn
                and cls._chat_conn.connection
                and not cls._chat_conn.connection.is_closed
        ):
            return

        try:
            if not settings.rabbitmq.host or not settings.rabbitmq.exchange_name or not settings.rabbitmq.queue_name:
                logger.warning(
                    "RabbitMQ 配置不完整，跳过初始化",
                    host=settings.rabbitmq.host,
                    exchange=settings.rabbitmq.exchange_name,
                    queue=settings.rabbitmq.queue_name,
                )
                return

            vhost = str(settings.rabbitmq.vhost or "/")
            # vhost 在 URL path segment 中需要做完整 URL encode（比如 "/" -> "%2F"）
            vhost_path = quote_plus(vhost)
            # 构建连接 URL（注意对特殊字符做 URL encode）
            connection_url = (
                f"amqp://{quote_plus(settings.rabbitmq.user)}:{quote_plus(settings.rabbitmq.password)}"
                f"@{settings.rabbitmq.host}:{settings.rabbitmq.port}/"
                f"{vhost_path}"
            )

            routing_key_prefix = str(settings.rabbitmq.routing_key_prefix or "").strip()
            if not routing_key_prefix:
                raise ValueError("RABBITMQ_ROUTING_KEY_PREFIX is required")
            routing_key = f"{routing_key_prefix}.*"
            cls._chat_conn = RabbitMQConnection(
                url=connection_url,
                exchange_name=settings.rabbitmq.exchange_name,
                routing_key=routing_key,
                queue_name=settings.rabbitmq.queue_name,
                prefetch_count=1,
                reconnect_delay=5,
                max_reconnect_attempts=5,
                exchange_type=aio_pika.ExchangeType.TOPIC,
            )
            await cls._chat_conn.connect()
            cls._bindings.add((settings.rabbitmq.queue_name, routing_key))

            crawler_exchange = str(
                settings.rabbitmq.crawler_exchange or ""
            ).strip()
            crawler_routing_key = str(
                settings.rabbitmq.crawler_routing_key or ""
            ).strip()
            crawler_queue = str(
                settings.rabbitmq.crawler_queue or ""
            ).strip()
            if crawler_exchange and crawler_queue and crawler_routing_key:
                cls._crawler_conn = RabbitMQConnection(
                    url=connection_url,
                    exchange_name=crawler_exchange,
                    routing_key=crawler_routing_key,
                    queue_name=crawler_queue,
                    prefetch_count=1,
                    reconnect_delay=5,
                    max_reconnect_attempts=5,
                    exchange_type=aio_pika.ExchangeType.DIRECT,
                )
                await cls._crawler_conn.connect()

            cls._initialized = True
            logger.info(
                "RabbitMQ 生产者初始化成功",
                host=settings.rabbitmq.host,
                exchange=settings.rabbitmq.exchange_name,
                queue=settings.rabbitmq.queue_name
            )
        except Exception as e:
            logger.error(
                "RabbitMQ 生产者初始化失败",
                error=str(e),
                exc_info=True
            )
            cls._chat_conn = None
            cls._crawler_conn = None
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
        if not cls._initialized or not cls._chat_conn or cls._chat_conn.exchange is None:
            raise RuntimeError("RabbitMQProducer is not initialized")

        if not tasks:
            return

        prefix = str(
            routing_key_prefix
            or settings.rabbitmq.routing_key_prefix
            or ""
        ).strip()
        if not prefix:
            raise ValueError("routing_key_prefix is required")
        queue_name = queue_name or settings.rabbitmq.queue_name
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
                await cls._chat_conn.exchange.publish(message, routing_key=routing_key)
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
                    settings.rabbitmq.outreach_routing_key_prefix or ""
                ).strip()
                queue_name = settings.rabbitmq.outreach_queue or None
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
        if not cls._initialized or not cls._crawler_conn or cls._crawler_conn.exchange is None:
            raise RuntimeError("RabbitMQProducer crawler exchange is not initialized")
        routing_key = str(
            settings.rabbitmq.crawler_routing_key or ""
        ).strip()
        if not routing_key:
            raise ValueError("RABBITMQ_CRAWLER_ROUTING_KEY is required")

        message_json = json.dumps(task, ensure_ascii=False, default=str)
        message = Message(
            message_json.encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await cls._crawler_conn.exchange.publish(message, routing_key=routing_key)

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
            settings.rabbitmq.outreach_routing_key_prefix or ""
        ).strip()
        queue_prefix = str(
            settings.rabbitmq.outreach_queue_prefix or ""
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
        if not cls._initialized or not cls._chat_conn or cls._chat_conn.exchange is None:
            raise RuntimeError("RabbitMQProducer is not initialized")
        if not action or not task_id:
            raise ValueError("action and task_id are required")

        control_prefix = str(
            settings.rabbitmq.outreach_control_routing_key_prefix or ""
        ).strip()
        control_queue = str(
            settings.rabbitmq.outreach_control_queue or ""
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
        await cls._chat_conn.exchange.publish(message, routing_key=routing_key)

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
        if not cls._chat_conn or not cls._chat_conn.channel or not cls._chat_conn.exchange:
            raise RuntimeError("RabbitMQProducer channel not ready")

        binding_key = f"{routing_key_prefix}.*"
        binding_key_id = (queue_name, binding_key)
        async with cls._bind_lock:
            if cache and binding_key_id in cls._bindings:
                return

            # 声明 DLX（全局共用）
            if not cls._chat_conn.dlx_exchange:
                dlx_name = f"{settings.rabbitmq.exchange_name}.dlx"
                cls._chat_conn.dlx_exchange = await cls._chat_conn.channel.declare_exchange(
                    dlx_name,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True,
                )

            dlq_name = f"{queue_name}.dead"
            dlq = await cls._chat_conn.channel.declare_queue(
                dlq_name,
                durable=dlq_durable,
                auto_delete=dlq_auto_delete,
                arguments=dlq_arguments or None,
            )
            dl_routing_key = f"{binding_key}.dead"
            await dlq.bind(cls._chat_conn.dlx_exchange, routing_key=dl_routing_key)

            # 声明主队列（带 DLX；确保与 consumer 声明参数一致）
            queue_args = dict(queue_arguments or {})
            queue_args.setdefault(
                "x-dead-letter-exchange", f"{settings.rabbitmq.exchange_name}.dlx"
            )
            queue_args.setdefault("x-dead-letter-routing-key", dl_routing_key)
            queue = await cls._chat_conn.channel.declare_queue(
                queue_name,
                durable=queue_durable,
                auto_delete=queue_auto_delete,
                exclusive=queue_exclusive,
                arguments=queue_args or None,
            )

            # 绑定队列到交换机（topic 通配符路由键）
            await queue.bind(cls._chat_conn.exchange, routing_key=binding_key)
            if cache:
                cls._bindings.add(binding_key_id)

    @classmethod
    async def close(cls) -> None:
        """关闭连接"""
        if cls._chat_conn:
            await cls._chat_conn.close()
        if cls._crawler_conn:
            await cls._crawler_conn.close()
        cls._chat_conn = None
        cls._crawler_conn = None
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
