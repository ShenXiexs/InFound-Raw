import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import aio_pika
from aio_pika.abc import AbstractRobustConnection

from apps.portal_seller_open_api.core.config import IFRabbitMQWebSTOMPSettings
from core_base import get_logger


class WebSocketNotificationService:
    """用户通知服务"""

    def __init__(self, settings: IFRabbitMQWebSTOMPSettings):
        self.settings = settings
        self.logger = get_logger(__name__)
        self._connection: Optional[AbstractRobustConnection] = None
        self._message_expiration = 7 * 24 * 60 * 60 * 1000  # 消息 TTL: 7 天

    async def get_connection(self) -> AbstractRobustConnection:
        """获取或创建 RabbitMQ 连接"""
        if self._connection is None or self._connection.is_closed:
            rabbitmq = self.settings

            # 构建 AMQP URL
            amqp_url = (
                f"amqp://{rabbitmq.username}:{rabbitmq.password}@"
                f"{rabbitmq.host}:{rabbitmq.port}/{rabbitmq.vhost}"
            )

            self._connection = await aio_pika.connect_robust(amqp_url)
            self.logger.info("Connected to RabbitMQ for notifications")

        return self._connection

    async def send_user_notification(
            self,
            user_id: str,
            title: str,
            content: str,
            message_type: str = "notification",
            extra_data: Optional[dict] = None,
    ) -> str:
        """
        向指定用户发送通知消息（持久化版本）

        Args:
            user_id: 用户 ID
            title: 消息标题
            content: 消息内容
            message_type: 消息类型（notification/order/system 等）
            extra_data: 额外数据

        Returns:
            str: 消息 ID
        """
        connection = await self.get_connection()

        async with connection:
            channel = await connection.channel()

            # 声明持久化 Exchange
            exchange = await channel.declare_exchange(
                self.settings.exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )

            # 预先声明持久化队列（推荐）
            queue_name = f"user.notification.{user_id}"
            queue = await channel.declare_queue(
                queue_name,
                durable=True,
                auto_delete=False,
                arguments={
                    'x-message-ttl': self._message_expiration,  # 消息 TTL: 7 天
                    'x-max-length': 1000,  # 最大消息数：1000
                }
            )

            # 绑定队列到 exchange
            await queue.bind(exchange, routing_key=f"user.notification.{user_id}")

            # 生成消息 ID
            message_id = f"msg-{uuid.uuid4()}"

            # 构建消息体
            message_body = {
                "messages": [
                    {
                        "id": message_id,
                        "title": title,
                        "content": content,
                        "type": message_type,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "userId": user_id,
                        **(extra_data or {})
                    }
                ]
            }

            # 发布持久化消息
            message = aio_pika.Message(
                body=json.dumps(message_body, ensure_ascii=False).encode('utf-8'),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,  # 持久化
                expiration=timedelta(milliseconds=self._message_expiration),  # 过期时间：7 天
                message_id=message_id,
            )

            routing_key = f"user.notification.{user_id}"
            await exchange.publish(message, routing_key=routing_key)

            self.logger.info(
                f"Notification sent to user {user_id}: {title} "
                f"(message_id: {message_id}, queue: {queue_name})"
            )

            return message_id

    async def close(self):
        """关闭连接"""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            self.logger.info("RabbitMQ connection closed")
