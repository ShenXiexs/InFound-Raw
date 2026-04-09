import asyncio
from typing import Optional, Union, Dict, List, Any

import aio_pika
from aio_pika import Connection, ExchangeType
from aio_pika.abc import (
    AbstractRobustConnection,
    AbstractQueue,
    AbstractChannel,
    AbstractExchange,
)

from core_base import get_logger
from .exceptions import RabbitMQConnectionError


class QueueBinding:
    """队列绑定配置"""

    def __init__(
        self,
        queue_name: str,
        routing_key: str,
        durable: bool = True,
        auto_delete: bool = False,
        exclusive: bool = False,
        arguments: Optional[Dict[str, Any]] = None,
    ):
        self.queue_name = queue_name
        self.routing_key = routing_key
        self.durable = durable
        self.auto_delete = auto_delete
        self.exclusive = exclusive
        self.arguments = arguments or {}


class RabbitMQConnection:
    """
    RabbitMQ 连接管理器（纯连接 + 按需绑定队列）

    特性：
    - 只管理连接和 Exchange
    - 队列按需绑定（可以不绑、绑一个、或多个）
    - 统一的 DLX/死信队列管理
    """

    def __init__(
        self,
        *,
        url: str,
        exchange_name: str,
        exchange_type: ExchangeType = ExchangeType.TOPIC,
        prefetch_count: int = 10,
        reconnect_delay: int = 5,
        max_reconnect_attempts: int = 10,
        dlq_durable: bool = True,
        dlq_auto_delete: bool = False,
    ):
        """
        初始化 RabbitMQ 连接配置

        Args:
            url: RabbitMQ 连接 URL
            exchange_name: 交换机名称
            exchange_type: 交换机类型（TOPIC/DIRECT/FANOUT）
            prefetch_count: 预取消息数
            reconnect_delay: 重连延迟（秒）
            max_reconnect_attempts: 最大重连次数
            dlq_durable: 死信队列是否持久化
            dlq_auto_delete: 死信队列是否自动删除
        """
        self.logger = get_logger("RabbitMQConnection")
        self.url = url
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type

        self.prefetch_count = prefetch_count
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.dlq_durable = bool(dlq_durable)
        self.dlq_auto_delete = bool(dlq_auto_delete)

        # 连接状态
        self.connection: Optional[Union[Connection, AbstractRobustConnection]] = None
        self.channel: Optional[AbstractChannel] = None
        self.exchange: Optional[AbstractExchange] = None
        self.dlx_exchange: Optional[AbstractExchange] = None

        # 队列管理（初始为空，按需添加）
        self.queues: Dict[str, AbstractQueue] = {}  # queue_name -> queue object
        self.bindings: Dict[str, str] = {}  # queue_name -> routing_key

        # Dead-letter exchange（全局共用）
        self.dlx_name = f"{exchange_name}.dlx"

    async def connect(self) -> None:
        """
        建立 RabbitMQ 连接并声明 Exchange 和 DLX

        注意：这里不会声明任何队列，队列需要后续调用 add_queue() 添加
        """
        if (
            self.connection
            and not self.connection.is_closed
            and self.channel
            and not self.channel.is_closed
            and self.exchange
        ):
            return

        self.logger.info(
            "Connecting to RabbitMQ",
            url=self.url,
            exchange=self.exchange_name,
        )

        last_exception: Optional[Exception] = None
        max_attempts = max(1, int(self.max_reconnect_attempts or 1))

        for attempt in range(1, max_attempts + 1):
            try:
                await self.close()

                # 1. 建立连接
                self.connection = await aio_pika.connect_robust(
                    self.url,
                    timeout=30,
                    heartbeat=60,
                )

                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=self.prefetch_count)

                # 2. 声明主交换机（支持 Topic/Direct/Fanout）
                self.exchange = await self.channel.declare_exchange(
                    self.exchange_name,
                    self.exchange_type,
                    durable=True,
                )

                # 3. 声明 DLX（死信交换机，全局共用）
                self.dlx_exchange = await self.channel.declare_exchange(
                    self.dlx_name,
                    ExchangeType.DIRECT,
                    durable=True,
                )

                self.logger.info(
                    "RabbitMQ connected successfully",
                    exchange=self.exchange_name,
                    exchange_type=str(self.exchange_type),
                )
                return

            except Exception as exc:
                last_exception = exc
                if attempt < max_attempts:
                    self.logger.warning(
                        "RabbitMQ connection failed, retrying...",
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay=self.reconnect_delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    self.logger.error(
                        "RabbitMQ connection failed after all retries",
                        attempts=max_attempts,
                        exc_info=exc,
                    )

        raise RabbitMQConnectionError(
            "Failed to connect to RabbitMQ after retries"
        ) from last_exception

    async def _declare_queue_with_dlq(
        self,
        queue_name: str,
        routing_key: str,
        durable: bool = True,
        auto_delete: bool = False,
        exclusive: bool = False,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> AbstractQueue:
        """
        内部方法：声明队列并自动配置死信队列

        Returns:
            AbstractQueue: 声明的队列对象
        """
        if not self.channel or not self.exchange or not self.dlx_exchange:
            raise RuntimeError("Connection not initialized. Call connect() first.")

        # 1. 声明该队列的死信队列
        dlq_name = f"{queue_name}.dead"
        dl_routing_key = f"{routing_key}.dead"

        dlq = await self.channel.declare_queue(
            dlq_name,
            durable=self.dlq_durable,
            auto_delete=self.dlq_auto_delete,
            arguments=None,
        )
        await dlq.bind(self.dlx_exchange, routing_key=dl_routing_key)

        # 2. 声明主队列（带 DLX 配置）
        queue_args = dict(arguments or {})
        queue_args.setdefault("x-dead-letter-exchange", self.dlx_name)
        queue_args.setdefault("x-dead-letter-routing-key", dl_routing_key)

        queue = await self.channel.declare_queue(
            queue_name,
            durable=durable,
            auto_delete=auto_delete,
            exclusive=exclusive,
            arguments=queue_args or None,
        )

        # 3. 绑定队列到主交换机
        await queue.bind(self.exchange, routing_key=routing_key)

        # 4. 记录绑定关系
        self.queues[queue_name] = queue
        self.bindings[queue_name] = routing_key

        self.logger.debug(
            "Queue declared and bound",
            queue_name=queue_name,
            routing_key=routing_key,
            dlq_name=dlq_name,
        )

        return queue

    async def add_queue(
        self,
        queue_name: str,
        routing_key: str,
        durable: bool = True,
        auto_delete: bool = False,
        exclusive: bool = False,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> AbstractQueue:
        """
        动态添加队列（运行时调用）

        Args:
            queue_name: 队列名称
            routing_key: 路由键
            durable: 是否持久化
            auto_delete: 是否自动删除
            exclusive: 是否独占
            arguments: 队列参数

        Returns:
            AbstractQueue: 新声明的队列对象
        """
        if queue_name in self.queues:
            self.logger.warning(
                "Queue already exists, skipping",
                queue_name=queue_name,
            )
            return self.queues[queue_name]

        if not self.connection or not self.channel:
            raise RuntimeError("Connection not initialized. Call connect() first.")

        return await self._declare_queue_with_dlq(
            queue_name=queue_name,
            routing_key=routing_key,
            durable=durable,
            auto_delete=auto_delete,
            exclusive=exclusive,
            arguments=arguments,
        )

    async def add_queues(
        self,
        queue_configs: List[QueueBinding],
    ) -> Dict[str, AbstractQueue]:
        """
        批量添加多个队列

        Args:
            queue_configs: 队列配置列表

        Returns:
            Dict[str, AbstractQueue]: {queue_name: queue_object}
        """
        result = {}
        for config in queue_configs:
            try:
                queue = await self.add_queue(
                    queue_name=config.queue_name,
                    routing_key=config.routing_key,
                    durable=config.durable,
                    auto_delete=config.auto_delete,
                    exclusive=config.exclusive,
                    arguments=config.arguments,
                )
                result[config.queue_name] = queue
            except Exception as e:
                self.logger.error(
                    "Failed to add queue",
                    queue_name=config.queue_name,
                    error=str(e),
                    exc_info=True,
                )

        return result

    async def bind_queue(
        self,
        queue_name: str,
        routing_key: str,
    ) -> Optional[AbstractQueue]:
        """
        绑定已存在的队列到交换机（队列必须已经存在）

        Args:
            queue_name: 队列名称
            routing_key: 路由键

        Returns:
            AbstractQueue: 队列对象
        """
        if not self.channel or not self.exchange:
            raise RuntimeError("Connection not initialized")

        # 尝试获取已存在的队列
        try:
            queue = await self.channel.declare_queue(
                queue_name,
                passive=True,  # 被动声明：如果队列不存在会报错
            )
        except Exception as e:
            self.logger.error(
                "Queue does not exist",
                queue_name=queue_name,
                error=str(e),
            )
            return None

        # 绑定队列到交换机
        await queue.bind(self.exchange, routing_key=routing_key)

        # 记录绑定关系
        self.queues[queue_name] = queue
        self.bindings[queue_name] = routing_key

        self.logger.info(
            "Queue bound to exchange",
            queue_name=queue_name,
            routing_key=routing_key,
        )

        return queue

    def get_queue(self, queue_name: str) -> Optional[AbstractQueue]:
        """获取指定队列对象"""
        return self.queues.get(queue_name)

    def get_routing_key(self, queue_name: str) -> Optional[str]:
        """获取指定队列的路由键"""
        return self.bindings.get(queue_name)

    def list_queues(self) -> List[str]:
        """列出所有已绑定的队列名称"""
        return list(self.queues.keys())

    async def remove_queue(self, queue_name: str) -> None:
        """
        移除队列（仅从内存中移除，不删除 RabbitMQ 中的队列）

        Args:
            queue_name: 队列名称
        """
        if queue_name in self.queues:
            del self.queues[queue_name]
        if queue_name in self.bindings:
            del self.bindings[queue_name]

        self.logger.info(
            "Queue removed from memory",
            queue_name=queue_name,
        )

    async def close(self) -> None:
        """关闭 RabbitMQ 连接及相关资源。"""
        try:
            if self.channel and not self.channel.is_closed:
                await self.channel.close()
        finally:
            self.channel = None
            self.queues.clear()
            self.bindings.clear()
            self.exchange = None
            self.dlx_exchange = None

        if self.connection and not self.connection.is_closed:
            await self.connection.close()

        self.connection = None
        self.logger.info("RabbitMQ connection closed")
