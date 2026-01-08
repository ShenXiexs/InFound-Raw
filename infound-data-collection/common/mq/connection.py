from typing import Optional

import aio_pika
from aio_pika import Connection, Channel, Queue, ExchangeType

from common.core.exceptions import RabbitMQConnectionError
from common.core.logger import get_logger

logger = get_logger()


class RabbitMQConnection:
    """RabbitMQ 连接管理（支持 Direct/Topic + DLX + 持久化）"""

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

        # 死信交换机
        self.dlx_name = f"{exchange_name}.dlx"
        self.dlq_name = f"{queue_name}.dead"
        self.dl_routing_key = f"{routing_key}.dead"

    async def connect(self) -> None:
        """建立 RabbitMQ 连接（包含 direct + DLX 声明）"""
        # 若连接或通道已失效，重建整个通道/队列声明，避免“channel invalid state”错误
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
            # 清理上一次残留状态，避免 RobustChannel 在后台 restore 时产生噪音报错
            await self.close()
            self.connection = await aio_pika.connect_robust(
                self.url,
                timeout=30,
                heartbeat=60
            )

            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=self.prefetch_count)

            # 1. 声明主交换机（direct）
            self.exchange = await self.channel.declare_exchange(
                self.exchange_name,
                self.exchange_type,
                durable=True
            )

            # 2. 声明死信交换机
            self.dlx_exchange = await self.channel.declare_exchange(
                self.dlx_name,
                ExchangeType.DIRECT,
                durable=True
            )

            # 3. 声明死信队列
            dlq = await self.channel.declare_queue(
                self.dlq_name,
                durable=self.dlq_durable,
                auto_delete=self.dlq_auto_delete,
                arguments=self.dlq_arguments or None,
            )
            await dlq.bind(self.dlx_exchange, routing_key=self.dl_routing_key)

            # 4. 声明主队列（带 DLX）
            queue_arguments = dict(self.queue_arguments or {})
            queue_arguments.setdefault("x-dead-letter-exchange", self.dlx_name)
            queue_arguments.setdefault("x-dead-letter-routing-key", self.dl_routing_key)
            self.queue = await self.channel.declare_queue(
                self.queue_name,
                durable=self.queue_durable,
                auto_delete=self.queue_auto_delete,
                exclusive=self.queue_exclusive,
                arguments=queue_arguments or None,
            )

            # 5. 将队列绑定到 direct exchange 上
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
            # 确保失败后不会保留半初始化的连接对象
            try:
                await self.close()
            except Exception:
                pass
            raise RabbitMQConnectionError("Failed to connect to RabbitMQ") from e

    async def close(self) -> None:
        """关闭 RabbitMQ 连接及相关资源"""
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
