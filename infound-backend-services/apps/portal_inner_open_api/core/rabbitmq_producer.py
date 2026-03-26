from __future__ import annotations

import json
from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4

import aio_pika
from aio_pika import Message

from core_base import get_logger
from core_mq import RabbitMQConnection
from core_mq.rabbitmq_setting import RabbitMQSettings


class RabbitMQProducer:
    """
    RabbitMQ 消息生产者（重构版 - 按需绑定队列）

    特性：
    - 只管理连接和 Exchange
    - 队列按需绑定（不强制主队列）
    - 统一的 DLX/死信队列管理
    """

    _logger = get_logger("RabbitMQProducer")
    _settings: Optional[RabbitMQSettings] = None
    _connection: Optional[RabbitMQConnection] = None
    _initialized: bool = False

    # 队列名称常量（用于统一管理）
    # QUEUE_CHATBOT = "chatbot.tasks.queue"
    # QUEUE_CRAWLER = "crawler.tasks.queue"
    # QUEUE_OUTREACH = "outreach.tasks.queue"
    # QUEUE_NOTIFICATION = "notification.queue"
    #
    # 路由键前缀常量
    # ROUTING_CHATBOT = "infound.chatbot.*"
    # ROUTING_CRAWLER = "infound.crawler.*"
    # ROUTING_OUTREACH = "infound.outreach.*"
    # ROUTING_NOTIFICATION = "infound.notification.*"

    @classmethod
    async def initialize(cls, settings: RabbitMQSettings) -> None:
        """
        初始化 RabbitMQ 连接和 Exchange

        注意：这里不会创建任何队列，队列需要后续按需添加
        """
        if cls._initialized and cls._connection and cls._connection.exchange:
            return

        try:
            if not settings.host or not settings.exchange_name:
                cls._logger.warning(
                    "RabbitMQ 配置不完整，跳过初始化",
                    host=settings.host,
                    exchange=settings.exchange_name,
                )
                return

            cls._settings = settings

            # 创建纯连接（不绑定任何队列）
            cls._connection = RabbitMQConnection(
                url=settings.url,
                exchange_name=settings.exchange_name,
                exchange_type=aio_pika.ExchangeType.TOPIC,
                prefetch_count=settings.prefetch_count or 10,
                reconnect_delay=settings.reconnect_delay,
                max_reconnect_attempts=settings.max_reconnect_attempts,
            )

            # 建立连接并声明 Exchange
            await cls._connection.connect()

            cls._initialized = True
            cls._logger.info(
                "RabbitMQ 生产者初始化成功（Topic Exchange，无主队列）",
                host=settings.host,
                exchange=settings.exchange_name,
            )
        except Exception as e:
            cls._logger.error("RabbitMQ 生产者初始化失败", error=str(e), exc_info=True)
            cls._connection = None
            cls._initialized = False

    @classmethod
    async def _get_connection(cls) -> RabbitMQConnection:
        """获取连接实例（确保已初始化）"""
        if not cls._connection:
            raise RuntimeError("RabbitMQProducer is not initialized")

        return cls._connection

    @classmethod
    async def ensure_queue(cls, queue_name: str, routing_key: str) -> None:
        """
        确保指定队列存在（如果不存在则创建）

        Args:
            queue_name: 队列名称
            routing_key: 路由键
        """
        conn = await cls._get_connection()

        if queue_name not in conn.queues:
            await conn.add_queue(
                queue_name=queue_name,
                routing_key=routing_key,
                durable=True,
            )
            cls._logger.info(
                "队列已创建",
                queue_name=queue_name,
                routing_key=routing_key,
            )

    @classmethod
    async def ensure_chatbot_queue(cls) -> None:
        """确保聊天机器人队列存在"""
        queue_setting = cls._settings.queues["chatbot"]
        await cls.ensure_queue(queue_setting.queue_name, queue_setting.routing_key_pattern)

    @classmethod
    async def ensure_crawler_queue(cls) -> None:
        """确保爬虫队列存在"""
        queue_setting = cls._settings.queues["crawler"]
        await cls.ensure_queue(queue_setting.queue_name, queue_setting.routing_key_pattern)

    @classmethod
    async def ensure_outreach_queue(cls) -> None:
        """确保建联队列存在"""
        queue_setting = cls._settings.queues["outreach"]
        await cls.ensure_queue(queue_setting.queue_name, queue_setting.routing_key_pattern)

    @classmethod
    async def publish(
            cls,
            body: Dict[str, Any],
            routing_key: str,
            message_id: Optional[str] = None,
            headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        发布消息到指定 routing_key

        Args:
            body: 消息体
            routing_key: 路由键（决定消息发送到哪个队列）
            message_id: 消息 ID
            headers: 自定义 headers
        """
        conn = await cls._get_connection()

        if not conn.exchange:
            raise RuntimeError("Exchange not initialized")

        msg_id = message_id or str(uuid4()).upper()

        message = Message(
            body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=msg_id,
            headers=headers or {},
            content_type="application/json",
        )

        await conn.exchange.publish(message, routing_key=routing_key)

        cls._logger.info(
            "Message published",
            message_id=msg_id,
            routing_key=routing_key,
            exchange=conn.exchange_name,
        )

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
        批量发布聊天机器人消息到 RabbitMQ

        注意：会自动创建 chatbot 队列（如果不存在）
        """
        # 确保队列存在
        await cls.ensure_chatbot_queue()

        if not tasks:
            return

        prefix = str(routing_key_prefix or cls._settings.routing_key_prefix).strip()
        if not prefix:
            raise ValueError("routing_key_prefix is required")

        # 使用 chatbot 的路由键
        routing_key = f"{prefix}.chatbot.batch"

        sent_count = 0
        try:
            for task in tasks:
                task_id = str(uuid4()).upper()
                message_body = [task]

                message_json = json.dumps(message_body, ensure_ascii=False, default=str)

                message = Message(
                    message_json.encode("utf-8"),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    headers={
                        "task_id": task_id,
                        "task_count": 1,
                    },
                )

                conn = await cls._get_connection()
                await conn.exchange.publish(message, routing_key=routing_key)
                sent_count += 1

            cls._logger.info(
                "聊天机器人消息已发送到 RabbitMQ",
                message_count=sent_count,
                routing_key=routing_key,
            )
        except Exception as e:
            cls._logger.error(
                "发送聊天机器人消息到 RabbitMQ 失败",
                message_count=sent_count,
                task_count=len(tasks),
                error=str(e),
                exc_info=True,
            )
            raise

    @classmethod
    async def publish_batch_outreach_chatbot_messages(
            cls,
            tasks: List[Dict[str, Any]],
    ) -> None:
        """
        发布建联聊天机器人消息到 RabbitMQ

        注意：会自动创建 outreach 队列（如果不存在）
        """
        if not tasks:
            return

        per_task_groups: Dict[Optional[str], List[Dict[str, Any]]] = {}
        for task in tasks:
            if not isinstance(task, dict):
                continue
            outreach_task_id = str(
                task.get("outreach_task_id") or task.get("outreachTaskId") or ""
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
                settings = cls._settings
                routing_key_prefix = str(
                    settings.outreach_routing_key_prefix or ""
                ).strip()
                queue_name = settings.outreach_queue or None
                if not routing_key_prefix or not queue_name:
                    raise ValueError(
                        "Outreach RabbitMQ routing key prefix/queue is required"
                    )
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
        """
        发布爬虫任务到 RabbitMQ

        注意：会自动创建 crawler 队列（如果不存在）
        """
        if not task:
            return

        # 确保队列存在
        await cls.ensure_crawler_queue()

        settings = cls._settings.rabbitmq

        # 使用 crawler 路由键
        routing_key = str(settings.crawler_routing_key or "").strip()
        if not routing_key:
            raise ValueError("RABBITMQ_CRAWLER_ROUTING_KEY is required")

        message_json = json.dumps(task, ensure_ascii=False, default=str)
        message = Message(
            message_json.encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )

        conn = await cls._get_connection()
        await conn.exchange.publish(message, routing_key=routing_key)

        cls._logger.info(
            "爬虫任务已发送",
            routing_key=routing_key,
            exchange=settings.exchange_name,
        )

    @classmethod
    async def ensure_outreach_task_queue(cls, task_id: str) -> Tuple[str, str]:
        """
        确保建联任务队列存在（动态队列，每个 task_id 一个队列）

        Returns:
            Tuple[str, str]: (queue_name, routing_key_prefix)
        """
        queue_name, routing_key_prefix = cls.build_outreach_task_binding(task_id)

        # 动态创建该 task_id 的专属队列
        await cls.ensure_queue(queue_name, f"{routing_key_prefix}.*")

        return queue_name, routing_key_prefix

    @classmethod
    def build_outreach_task_binding(cls, task_id: str) -> Tuple[str, str]:
        """构建建联任务的绑定关系"""
        if not task_id:
            raise ValueError("task_id is required for outreach queue")

        settings = cls._settings.queues["outreach"]
        routing_prefix = str(settings.routing_key_pattern or "").strip()
        queue_prefix = str(settings.outreach_queue_prefix or "").strip()

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
        """发布建联控制消息"""
        # 确保控制队列存在
        settings = cls._settings.rabbitmq
        control_queue = str(settings.outreach_control_queue or "").strip()
        control_prefix = str(settings.outreach_control_routing_key_prefix or "").strip()

        if control_queue and control_prefix:
            await cls.ensure_queue(control_queue, f"{control_prefix}.*")

        if not action or not task_id:
            raise ValueError("action and task_id are required")

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

        conn = await cls._get_connection()
        await conn.exchange.publish(message, routing_key=routing_key)

    @classmethod
    async def list_queues(cls) -> List[str]:
        """列出当前已绑定的所有队列"""
        if not cls._connection:
            return []
        return cls._connection.list_queues()

    @classmethod
    async def close(cls) -> None:
        """关闭连接"""
        if cls._connection:
            await cls._connection.close()

        cls._connection = None
        cls._initialized = False

        cls._logger.info("RabbitMQ 生产者连接已关闭")


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
