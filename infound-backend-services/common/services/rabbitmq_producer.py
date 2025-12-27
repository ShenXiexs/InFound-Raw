from __future__ import annotations

import json
from typing import List, Optional, Dict, Any
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
    """RabbitMQ producer for batching chatbot messages."""

    _connection: Optional[AbstractConnection] = None
    _channel: Optional[Channel] = None
    _exchange: Optional[Exchange] = None
    _initialized: bool = False

    @classmethod
    async def initialize(cls) -> None:
        """Initialize RabbitMQ connection, channel, and exchange."""
        if cls._initialized and cls._connection and not cls._connection.is_closed:
            return

        try:
            if not settings.RABBITMQ_HOST or not settings.RABBITMQ_EXCHANGE or not settings.RABBITMQ_QUEUE:
                logger.warning(
                    "RabbitMQ config incomplete; skipping initialization",
                    host=settings.RABBITMQ_HOST,
                    exchange=settings.RABBITMQ_EXCHANGE,
                    queue=settings.RABBITMQ_QUEUE,
                )
                return

            vhost = str(getattr(settings, "RABBITMQ_VHOST", "/") or "/")
            # vhost must be URL-encoded in the path segment (e.g., "/" -> "%2F")
            vhost_path = quote_plus(vhost)
            # Build connection URL (encode special characters)
            connection_url = (
                f"amqp://{quote_plus(settings.RABBITMQ_USER)}:{quote_plus(settings.RABBITMQ_PASSWORD)}"
                f"@{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/"
                f"{vhost_path}"
            )

            # Create connection (robust with auto-reconnect)
            cls._connection = await aio_pika.connect_robust(connection_url)

            # Create channel
            cls._channel = await cls._connection.channel()

            # Declare exchange (topic)
            cls._exchange = await cls._channel.declare_exchange(
                settings.RABBITMQ_EXCHANGE,
                aio_pika.ExchangeType.TOPIC,
                durable=True  # durable exchange
            )

            routing_key_prefix = str(getattr(settings, "RABBITMQ_ROUTING_KEY_PREFIX", "") or "").strip()
            if not routing_key_prefix:
                raise ValueError("RABBITMQ_ROUTING_KEY_PREFIX is required")

            binding_key = f"{routing_key_prefix}.*"

            # Declare DLX/DLQ (aligned with consumer)
            dlx_name = f"{settings.RABBITMQ_EXCHANGE}.dlx"
            dlx_exchange = await cls._channel.declare_exchange(
                dlx_name,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            dlq_name = f"{settings.RABBITMQ_QUEUE}.dead"
            dlq = await cls._channel.declare_queue(dlq_name, durable=True)
            dl_routing_key = f"{binding_key}.dead"
            await dlq.bind(dlx_exchange, routing_key=dl_routing_key)

            # Declare main queue (with DLX; align with consumer args)
            queue = await cls._channel.declare_queue(
                settings.RABBITMQ_QUEUE,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": dlx_name,
                    "x-dead-letter-routing-key": dl_routing_key,
                },
            )

            # Bind queue to exchange (topic routing)
            await queue.bind(cls._exchange, routing_key=binding_key)

            cls._initialized = True
            logger.info(
                "RabbitMQ producer initialized",
                host=settings.RABBITMQ_HOST,
                exchange=settings.RABBITMQ_EXCHANGE,
                queue=settings.RABBITMQ_QUEUE
            )
        except Exception as e:
            logger.error(
                "RabbitMQ producer initialization failed",
                error=str(e),
                exc_info=True
            )
            cls._connection = None
            cls._channel = None
            cls._exchange = None
            cls._initialized = False
            # Do not raise; MQ is optional for the service

    @classmethod
    async def publish_batch_chatbot_messages(
        cls,
        tasks: List[Dict[str, Any]],
    ) -> None:
        """
        Publish chatbot messages in batch (each task enqueued separately).

        Args:
            tasks: list of tasks, each includes:
                - region: region
                - platformCreatorId: creator ID on the platform
                - messages: [{type, content, meta?}, ...]
        """
        if not cls._initialized or cls._exchange is None:
            raise RuntimeError("RabbitMQProducer is not initialized")

        if not tasks:
            return

        routing_key = f"{settings.RABBITMQ_ROUTING_KEY_PREFIX}.batch"
        sent_count = 0
        try:
            for task in tasks:
                # Generate message ID (header only; body is a single task)
                task_id = f"TASK-{str(uuid4()).upper()}"
                message_body = [task]

                # Serialize to JSON
                message_json = json.dumps(message_body, ensure_ascii=False, default=str)

                # Create message (persistent)
                message = Message(
                    message_json.encode("utf-8"),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    headers={
                        "task_id": task_id,
                        "task_count": 1,
                    },
                )

                # Publish message
                await cls._exchange.publish(message, routing_key=routing_key)
                sent_count += 1

            logger.info(
                "Chatbot messages published to RabbitMQ",
                message_count=sent_count,
                routing_key=routing_key,
            )
        except Exception as e:
            logger.error(
                "Failed to publish chatbot messages to RabbitMQ",
                message_count=sent_count,
                task_count=len(tasks),
                error=str(e),
                exc_info=True,
            )
            # Raise so scheduler can decide whether to advance schedule (avoid drops)
            raise

    @classmethod
    async def close(cls) -> None:
        """Close connections."""
        if cls._channel and not cls._channel.is_closed:
            await cls._channel.close()
        if cls._connection and not cls._connection.is_closed:
            await cls._connection.close()
        cls._connection = None
        cls._channel = None
        cls._exchange = None
        cls._initialized = False
        logger.info("RabbitMQ producer connection closed")


