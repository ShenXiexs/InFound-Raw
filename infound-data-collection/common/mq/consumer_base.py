import asyncio
import json
from abc import ABC, abstractmethod
from typing import Dict, Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common.core.exceptions import MessageProcessingError, NonRetryableMessageError
from common.core.logger import get_logger
from .connection import RabbitMQConnection

logger = get_logger()


def _parse_message_body(body_bytes: bytes) -> Dict[str, Any]:
    """Parse message body (JSON)."""
    try:
        return json.loads(body_bytes.decode('utf-8'))
    except Exception as e:
        raise ValueError(f"Failed to parse message body: {str(e)}") from e


class ConsumerBase(ABC):
    """Base consumer class; all consumers inherit this."""

    def __init__(self, rabbitmq_connection: RabbitMQConnection):
        self.rabbitmq_conn = rabbitmq_connection
        self.consumer_name = self.__class__.__name__.lower().replace("consumer", "")
        self.logger = logger.bind(consumer=self.consumer_name)

    @abstractmethod
    async def process_message_body(self, message_id: str, body: Dict[str, Any]) -> None:
        """
        Abstract handler for message body (implemented by subclasses).
        :param message_id: message ID
        :param body: parsed message body
        """
        pass

    async def process_message(self, message: AbstractIncomingMessage) -> None:
        """Unified message handler (parse, log, error handling)."""
        message_id = message.message_id
        self.logger.info("Received message", message_id=message_id, routing_key=message.routing_key)

        # At-most-once: broker auto-acks the delivery; we must NOT requeue.
        if getattr(self.rabbitmq_conn, "at_most_once", False):
            await self._process_message_at_most_once(message)
            return

        try:
            body = _parse_message_body(message.body)
            self.logger.debug("Parsed message body", message_id=message_id, body=body)

            await self.process_message_body(message_id, body)

            self.logger.info("Message processed successfully", message_id=message_id)
            await message.ack()
        except ValueError as e:
            self.logger.error("Invalid message format", message_id=message_id, error=str(e))
            await message.reject(requeue=False)
        except NonRetryableMessageError as e:
            self.logger.error("Non-retryable message error", message_id=message_id, error=str(e), exc_info=True)
            await message.reject(requeue=False)
        except MessageProcessingError as e:
            self.logger.error("Message processing failed", message_id=message_id, error=str(e), exc_info=True)
            await message.reject(requeue=False)
        except Exception:
            self.logger.critical("Unexpected error processing message", message_id=message_id, exc_info=True)
            await message.reject(requeue=False)

    async def _process_message_at_most_once(self, message: AbstractIncomingMessage) -> None:
        message_id = message.message_id
        try:
            body = _parse_message_body(message.body)
        except Exception as exc:
            self.logger.error(
                "Invalid message format (at_most_once; dropping)",
                message_id=message_id,
                error=str(exc),
            )
            await self._publish_to_dead_letter(message.body, message_id, reason=str(exc))
            return

        try:
            self.logger.debug("Parsed message body", message_id=message_id, body=body)
            await self.process_message_body(message_id, body)
            self.logger.info("Message processed successfully (at_most_once)", message_id=message_id)
        except Exception as exc:
            self.logger.error(
                "Message processing failed (at_most_once; dropping)",
                message_id=message_id,
                error=str(exc),
                exc_info=True,
            )
            await self._publish_to_dead_letter(message.body, message_id, reason=str(exc))

    async def _publish_to_dead_letter(self, body: bytes, message_id: str | None, reason: str) -> None:
        try:
            dlx_exchange = getattr(self.rabbitmq_conn, "dlx_exchange", None)
            if not dlx_exchange:
                return
            headers = {"x-error": reason}
            if message_id:
                headers["x-original-message-id"] = message_id
            await dlx_exchange.publish(
                aio_pika.Message(
                    body=body,
                    message_id=message_id,
                    headers=headers,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=self.rabbitmq_conn.dl_routing_key,
            )
        except Exception:
            self.logger.warning("Failed to publish to dead-letter exchange", exc_info=True)

    async def start(self) -> None:
        """Start consumer."""
        self.logger.info("Starting consumer", queue=self.rabbitmq_conn.queue_name)

        while True:
            try:
                # Ensure RabbitMQ connection
                await self.rabbitmq_conn.connect()

                # Log binding/backlog for debugging
                backlog = None
                try:
                    result = getattr(self.rabbitmq_conn.queue, "declaration_result", None)
                    backlog = result.message_count if result else None
                except Exception:
                    backlog = None
                self.logger.info(
                    "Consumer binding ready",
                    exchange=self.rabbitmq_conn.exchange_name,
                    routing_key=self.rabbitmq_conn.routing_key,
                    queue=self.rabbitmq_conn.queue_name,
                    backlog=backlog,
                )

                # Start consuming
                await self.rabbitmq_conn.queue.consume(
                    self.process_message,
                    no_ack=bool(getattr(self.rabbitmq_conn, "at_most_once", False))
                )

                self.logger.info("Consumer started successfully", queue=self.rabbitmq_conn.queue_name)
                # Keep consuming
                while True:
                    await asyncio.sleep(1)

            except Exception as e:
                self.logger.error("Consumer error, restarting...", error=str(e), exc_info=True)
                # Clean up to avoid noisy robust channel callbacks.
                try:
                    await self.rabbitmq_conn.close()
                except Exception:
                    pass
                await asyncio.sleep(self.rabbitmq_conn.reconnect_delay)

    async def stop(self) -> None:
        """Stop consumer (cleanup)."""
        self.logger.info("Stopping consumer")
        await self.rabbitmq_conn.close()
        self.logger.info("Consumer stopped successfully")
