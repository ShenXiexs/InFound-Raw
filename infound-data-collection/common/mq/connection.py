from typing import Optional

import aio_pika
from aio_pika import Connection, Channel, Queue, ExchangeType

from common.core.exceptions import RabbitMQConnectionError
from common.core.logger import get_logger

logger = get_logger()


class RabbitMQConnection:
    """RabbitMQ connection manager (Direct/Topic + DLX + durability)."""

    def __init__(
            self,
            url: str,
            exchange_name: str,
            routing_key: str,
            queue_name: str,
            at_most_once: bool = False,
            prefetch_count: int = 10,
            reconnect_delay: int = 5,
            max_reconnect_attempts: int = 10,
            exchange_type: ExchangeType = ExchangeType.DIRECT,
    ):
        self.url = url
        self.queue_name = queue_name
        self.routing_key = routing_key
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self.at_most_once = bool(at_most_once)

        self.prefetch_count = prefetch_count
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts

        self.connection: Optional[Connection] = None
        self.channel: Optional[Channel] = None
        self.queue: Optional[Queue] = None
        self.exchange = None
        self.dlx_exchange = None

        # Dead-letter exchange/queue
        self.dlx_name = f"{exchange_name}.dlx"
        self.dlq_name = f"{queue_name}.dead"
        self.dl_routing_key = f"{routing_key}.dead"

    async def connect(self) -> None:
        """Connect to RabbitMQ (declare exchange + DLX)."""
        # Recreate channel/queue if stale to avoid invalid channel state.
        if (
            self.connection
            and not self.connection.is_closed
            and self.channel
            and not self.channel.is_closed
            and self.queue
        ):
            return

        logger.info("Connecting to RabbitMQ", url=self.url, queue=self.queue_name)
        try:
            # Clear prior state to avoid noisy restore errors.
            await self.close()
            self.connection = await aio_pika.connect_robust(
                self.url,
                timeout=30,
                heartbeat=60
            )

            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=self.prefetch_count)

            # 1. Declare main exchange
            self.exchange = await self.channel.declare_exchange(
                self.exchange_name,
                self.exchange_type,
                durable=True
            )

            # 2. Declare DLX
            self.dlx_exchange = await self.channel.declare_exchange(
                self.dlx_name,
                ExchangeType.DIRECT,
                durable=True
            )

            # 3. Declare DLQ
            dlq = await self.channel.declare_queue(
                self.dlq_name,
                durable=True
            )
            await dlq.bind(self.dlx_exchange, routing_key=self.dl_routing_key)

            # 4. Declare main queue (with DLX)
            self.queue = await self.channel.declare_queue(
                self.queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": self.dlx_name,
                    "x-dead-letter-routing-key": self.dl_routing_key,
                }
            )

            # 5. Bind queue to exchange
            await self.queue.bind(self.exchange, routing_key=self.routing_key)

            consumer_count = None
            backlog = None
            try:
                result = self.queue.declaration_result
                backlog = getattr(result, "message_count", None)
                consumer_count = getattr(result, "consumer_count", None)
            except Exception:
                pass

            logger.info(
                "RabbitMQ connected successfully",
                queue=self.queue_name,
                backlog=backlog,
                consumer_count=consumer_count,
            )

        except Exception as e:
            logger.error("RabbitMQ connection failed", error=str(e), exc_info=True)
            # Ensure no half-initialized connection remains
            try:
                await self.close()
            except Exception:
                pass
            raise RabbitMQConnectionError("Failed to connect to RabbitMQ") from e

    async def close(self) -> None:
        """Close RabbitMQ connection and related resources."""
        had_resource = bool(
            (self.channel and not self.channel.is_closed)
            or (self.connection and not self.connection.is_closed)
        )
        try:
            if self.channel and not self.channel.is_closed:
                await self.channel.close()
        finally:
            self.channel = None
            self.queue = None
            self.exchange = None
            self.dlx_exchange = None
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
        self.connection = None
        if had_resource:
            logger.info("RabbitMQ connection closed")
