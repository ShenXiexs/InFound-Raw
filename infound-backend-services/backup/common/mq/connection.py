import asyncio
from typing import Optional

import aio_pika
from aio_pika import Connection, Channel, Queue, ExchangeType

from common.core.exceptions import RabbitMQConnectionError
from common.core.logger import get_logger

logger = get_logger()


class RabbitMQConnection:
    """RabbitMQ 连接管理（支持 exchange + DLX + 持久化），支持重试。"""

    def __init__(
        self,
        *,
        url: str,
        exchange_name: str,
        routing_key: str,
        queue_name: str,
        at_most_once: bool = False,
        prefetch_count: int = 10,
        reconnect_delay: int = 5,
        max_reconnect_attempts: int = 10,
        exchange_type: ExchangeType = ExchangeType.DIRECT,
        queue_arguments: Optional[dict] = None,
        queue_durable: bool = True,
        queue_auto_delete: bool = False,
        queue_exclusive: bool = False,
        dlq_arguments: Optional[dict] = None,
        dlq_durable: bool = True,
        dlq_auto_delete: bool = False,
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
        self.queue_arguments = queue_arguments or {}
        self.queue_durable = bool(queue_durable)
        self.queue_auto_delete = bool(queue_auto_delete)
        self.queue_exclusive = bool(queue_exclusive)
        self.dlq_arguments = dlq_arguments or {}
        self.dlq_durable = bool(dlq_durable)
        self.dlq_auto_delete = bool(dlq_auto_delete)

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
        """建立 RabbitMQ 连接（包含 exchange + DLX 声明），支持重试。"""
        if (
            self.connection
            and not self.connection.is_closed
            and self.channel
            and not self.channel.is_closed
            and self.queue
        ):
            return

        logger.info("Connecting to RabbitMQ", url=self.url, queue=self.queue_name)

        last_exception: Optional[Exception] = None
        max_attempts = max(1, int(self.max_reconnect_attempts or 1))
        for attempt in range(1, max_attempts + 1):
            try:
                await self.close()
                self.connection = await aio_pika.connect_robust(
                    self.url,
                    timeout=30,
                    heartbeat=60,
                )

                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=self.prefetch_count)

                # 1. 主交换机
                try:
                    self.exchange = await self.channel.declare_exchange(
                        self.exchange_name,
                        self.exchange_type,
                        durable=True,
                    )
                except Exception as exc:
                    logger.error(
                        "Exchange declaration failed; existing exchange may mismatch type/durable",
                        exchange_name=self.exchange_name,
                        expected_type=str(self.exchange_type),
                        expected_durable=True,
                        error=str(exc),
                        exc_info=True,
                    )
                    raise RabbitMQConnectionError(
                        f"Exchange {self.exchange_name} declaration failed."
                    ) from exc

                # 2. DLX
                try:
                    self.dlx_exchange = await self.channel.declare_exchange(
                        self.dlx_name,
                        ExchangeType.DIRECT,
                        durable=True,
                    )
                except Exception as exc:
                    logger.error(
                        "DLX exchange declaration failed",
                        exchange_name=self.dlx_name,
                        expected_type="DIRECT",
                        expected_durable=True,
                        error=str(exc),
                        exc_info=True,
                    )
                    raise RabbitMQConnectionError(
                        f"DLX exchange {self.dlx_name} declaration failed."
                    ) from exc

                # 3. DLQ
                try:
                    dlq = await self.channel.declare_queue(
                        self.dlq_name,
                        durable=self.dlq_durable,
                        auto_delete=self.dlq_auto_delete,
                        arguments=self.dlq_arguments or None,
                    )
                    await dlq.bind(self.dlx_exchange, routing_key=self.dl_routing_key)
                except Exception as exc:
                    logger.error(
                        "DLQ declaration/bind failed",
                        queue_name=self.dlq_name,
                        routing_key=self.dl_routing_key,
                        error=str(exc),
                        exc_info=True,
                    )
                    raise RabbitMQConnectionError(
                        f"DLQ {self.dlq_name} declaration/bind failed: {exc}"
                    ) from exc

                # 4. 主队列
                queue_arguments = dict(self.queue_arguments or {})
                queue_arguments.setdefault("x-dead-letter-exchange", self.dlx_name)
                queue_arguments.setdefault("x-dead-letter-routing-key", self.dl_routing_key)
                try:
                    self.queue = await self.channel.declare_queue(
                        self.queue_name,
                        durable=self.queue_durable,
                        auto_delete=self.queue_auto_delete,
                        exclusive=self.queue_exclusive,
                        arguments=queue_arguments or None,
                    )
                except Exception as exc:
                    logger.error(
                        "Queue declaration failed",
                        queue_name=self.queue_name,
                        error=str(exc),
                        exc_info=True,
                    )
                    raise RabbitMQConnectionError(
                        f"Queue {self.queue_name} declaration failed: {exc}"
                    ) from exc

                # 5. 绑定队列到交换机
                try:
                    await self.queue.bind(self.exchange, routing_key=self.routing_key)
                except Exception as exc:
                    logger.error(
                        "Queue bind failed",
                        queue_name=self.queue_name,
                        exchange_name=self.exchange_name,
                        routing_key=self.routing_key,
                        error=str(exc),
                        exc_info=True,
                    )
                    raise RabbitMQConnectionError(
                        f"Queue {self.queue_name} bind to {self.exchange_name} failed: {exc}"
                    ) from exc

                logger.info("RabbitMQ connected successfully", queue=self.queue_name)
                return

            except Exception as exc:
                last_exception = exc
                if attempt < max_attempts:
                    logger.warning(
                        "RabbitMQ connection failed, retrying...",
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay=self.reconnect_delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    logger.error(
                        "RabbitMQ connection failed after all retries",
                        attempts=max_attempts,
                        exc_info=exc,
                    )

        raise RabbitMQConnectionError("Failed to connect to RabbitMQ after retries") from last_exception

    async def close(self) -> None:
        """关闭 RabbitMQ 连接及相关资源。"""
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
