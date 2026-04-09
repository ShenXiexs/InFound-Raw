import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Dict

from aio_pika.abc import AbstractIncomingMessage

from core_base import get_logger
from .connection import RabbitMQConnection
from .exceptions import MessageProcessingError


def _parse_message_body(body_bytes: bytes) -> Dict[str, Any]:
    """解析消息体（支持 JSON 格式）"""
    try:
        return json.loads(body_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Failed to parse message body: {exc}") from exc


class ConsumerBase(ABC):
    """消费端基类，所有消费端继承此类"""

    def __init__(self, rabbitmq_connection: RabbitMQConnection):
        self.rabbitmq_conn = rabbitmq_connection
        self.consumer_name = self.__class__.__name__.lower().replace("consumer", "")
        self.logger = get_logger().bind(consumer=self.consumer_name)

    @abstractmethod
    async def process_message_body(self, message_id: str, body: Dict[str, Any]) -> None:
        """处理消息体（子类必须实现）"""
        raise NotImplementedError

    async def process_message(self, message: AbstractIncomingMessage) -> None:
        """统一消息处理入口（包含解析、日志、错误处理）"""
        async with message.process():
            message_id = message.message_id
            self.logger.info(
                "Received message",
                message_id=message_id,
                routing_key=message.routing_key,
            )

            try:
                body = _parse_message_body(message.body)
                self.logger.debug(
                    "Parsed message body", message_id=message_id, body=body
                )

                await self.process_message_body(message_id, body)

                self.logger.info(
                    "Message processed successfully", message_id=message_id
                )

            except ValueError as exc:
                self.logger.error(
                    "Invalid message format", message_id=message_id, error=str(exc)
                )
                await message.reject(requeue=False)
            except MessageProcessingError as exc:
                self.logger.error(
                    "Message processing failed",
                    message_id=message_id,
                    error=str(exc),
                    exc_info=True,
                )
                await message.reject(requeue=True)
            except Exception:
                self.logger.critical(
                    "Unexpected error processing message",
                    message_id=message_id,
                    exc_info=True,
                )
                await message.reject(requeue=False)

    async def start(self) -> None:
        """启动消费端"""
        self.logger.info("Starting consumer", queue=self.rabbitmq_conn.queue_name)

        while True:
            try:
                await self.rabbitmq_conn.connect()

                await self.rabbitmq_conn.queue.consume(
                    self.process_message,
                    no_ack=False,
                )

                self.logger.info(
                    "Consumer started successfully", queue=self.rabbitmq_conn.queue_name
                )
                while True:
                    await asyncio.sleep(1)

            except Exception as exc:
                self.logger.error(
                    "Consumer error, restarting...", error=str(exc), exc_info=True
                )
                await asyncio.sleep(self.rabbitmq_conn.reconnect_delay)

    async def stop(self) -> None:
        """停止消费端（清理资源）"""
        self.logger.info("Stopping consumer")
        await self.rabbitmq_conn.close()
        self.logger.info("Consumer stopped successfully")
