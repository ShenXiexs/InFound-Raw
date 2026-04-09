import json
import uuid
from abc import ABC
from typing import Any, Dict, Optional

from aio_pika import DeliveryMode, Message

from core_base import get_logger
from .connection import RabbitMQConnection
from .exceptions import RabbitMQConnectionError


class ProducerBase(ABC):
    """生产者基类（Direct + 持久化 + 统一发布规范）"""

    def __init__(self, rabbitmq_connection: RabbitMQConnection):
        self.rabbitmq_conn = rabbitmq_connection
        self.producer_name = self.__class__.__name__.lower().replace("producer", "")
        self.logger = get_logger().bind(producer=self.producer_name)

    async def publish(
        self,
        body: Dict[str, Any],
        *,
        routing_key: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
    ) -> None:
        """
        发布消息（统一入口）

        :param body: 消息体（dict，会自动 JSON 序列化）
        :param routing_key: 覆盖默认 routing_key（可选）
        :param headers: 自定义 headers
        :param message_id: 指定 message_id（不传自动生成）
        """

        await self.rabbitmq_conn.connect()

        exchange = self.rabbitmq_conn.exchange
        if exchange is None:
            raise RabbitMQConnectionError("Exchange not initialized")

        rk = routing_key or self.rabbitmq_conn.routing_key
        msg_id = message_id or str(uuid.uuid4())

        message = Message(
            body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=msg_id,
            headers=headers or {},
            content_type="application/json",
        )

        await exchange.publish(message, routing_key=rk)

        self.logger.info(
            "Message published",
            message_id=msg_id,
            routing_key=rk,
            exchange=self.rabbitmq_conn.exchange_name,
        )
