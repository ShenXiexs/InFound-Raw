import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Callable, Awaitable
from urllib.parse import quote_plus

from aio_pika import ExchangeType

from common.core.config import get_settings
from common.core.logger import get_logger
from common.mq.connection import RabbitMQConnection
from common.mq.consumer_base import ConsumerBase

from apps.sample_chatbot.crawler_consumer import (
    CrawlerConsumer as SampleChatbotConsumer,
)
from apps.outreach_chatbot.crawler_consumer import (
    CrawlerConsumer as OutreachChatbotConsumer,
)

OUTREACH_QUEUE_EXPIRES_MS = 30 * 60 * 1000


@dataclass
class TaskConsumerState:
    consumer: OutreachChatbotConsumer
    task: asyncio.Task


class OutreachControlConsumer(ConsumerBase):
    """Consumes control messages to start/stop per-task outreach consumers."""

    def __init__(
        self,
        *,
        handler: Callable[[str, str, Optional[str], Optional[str]], Awaitable[None]],
        rabbitmq_config: Dict[str, Any],
    ) -> None:
        settings = get_settings()
        amqp_url = (
            f"amqp://{quote_plus(settings.RABBITMQ_USERNAME)}:"
            f"{quote_plus(settings.RABBITMQ_PASSWORD)}@"
            f"{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/"
            f"{quote_plus(settings.RABBITMQ_VHOST)}"
        )
        rabbitmq_conn = RabbitMQConnection(
            url=amqp_url,
            exchange_name=rabbitmq_config.get(
                "exchange_name", settings.RABBITMQ_EXCHANGE_NAME
            ),
            routing_key=rabbitmq_config.get(
                "routing_key", settings.RABBITMQ_ROUTING_KEY
            ),
            queue_name=rabbitmq_config.get(
                "queue_name", settings.RABBITMQ_QUEUE_NAME
            ),
            at_most_once=rabbitmq_config.get(
                "at_most_once", getattr(settings, "RABBITMQ_AT_MOST_ONCE", False)
            ),
            prefetch_count=rabbitmq_config.get(
                "prefetch_count", settings.RABBITMQ_PREFETCH_COUNT
            ),
            reconnect_delay=rabbitmq_config.get(
                "reconnect_delay", settings.RABBITMQ_RECONNECT_DELAY
            ),
            max_reconnect_attempts=rabbitmq_config.get(
                "max_reconnect_attempts", settings.RABBITMQ_MAX_RECONNECT_ATTEMPTS
            ),
            exchange_type=ExchangeType.TOPIC,
        )
        super().__init__(rabbitmq_conn)
        self._handler = handler
        self.logger = get_logger().bind(consumer="outreach_control")

    async def process_message_body(self, message_id: str, body: object) -> None:
        if not isinstance(body, dict):
            self.logger.warning("Unsupported control message body", message_id=message_id)
            return

        action = str(body.get("action") or "").strip().lower()
        task_id = str(body.get("task_id") or body.get("taskId") or "").strip()
        queue_name = str(body.get("queue_name") or body.get("queueName") or "").strip() or None
        routing_key_prefix = str(
            body.get("routing_key_prefix") or body.get("routingKeyPrefix") or ""
        ).strip() or None

        if not action or not task_id:
            self.logger.warning(
                "Control message missing action/task_id",
                message_id=message_id,
                action=action,
                task_id=task_id,
            )
            return

        await self._handler(action, task_id, queue_name, routing_key_prefix)


class CrawlerConsumer:
    """Unified chatbot consumer running sample + outreach queues in one process."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = get_logger().bind(consumer="unified_chatbot")
        self._tasks: List[asyncio.Task] = []
        self._outreach_task_consumers: Dict[str, TaskConsumerState] = {}
        self._control_lock = asyncio.Lock()

        sample_config = self._build_rabbitmq_config(
            prefix="RABBITMQ_SAMPLE",
            defaults={
                "exchange_name": self.settings.RABBITMQ_EXCHANGE_NAME,
                "routing_key": "chatbot.sample.*",
                "queue_name": "chatbot.sample.queue.topic",
                "prefetch_count": getattr(self.settings, "RABBITMQ_PREFETCH_COUNT", 1),
                "at_most_once": getattr(self.settings, "RABBITMQ_AT_MOST_ONCE", False),
            },
        )
        outreach_config = self._build_rabbitmq_config(
            prefix="RABBITMQ_OUTREACH",
            defaults={
                "exchange_name": self.settings.RABBITMQ_EXCHANGE_NAME,
                "routing_key": "chatbot.outreach.*",
                "queue_name": "chatbot.outreach.queue.topic",
                "prefetch_count": getattr(self.settings, "RABBITMQ_PREFETCH_COUNT", 1),
                "at_most_once": getattr(self.settings, "RABBITMQ_AT_MOST_ONCE", False),
            },
        )
        control_config = self._build_rabbitmq_config(
            prefix="RABBITMQ_OUTREACH_CONTROL",
            defaults={
                "exchange_name": self.settings.RABBITMQ_EXCHANGE_NAME,
                "routing_key": "chatbot.outreach.control.*",
                "queue_name": "chatbot.outreach.control.queue",
                "prefetch_count": 1,
                "at_most_once": getattr(self.settings, "RABBITMQ_AT_MOST_ONCE", False),
            },
        )

        self.sample_consumer = SampleChatbotConsumer(rabbitmq_config=sample_config)
        self.outreach_consumer = OutreachChatbotConsumer(rabbitmq_config=outreach_config)
        self.control_consumer = OutreachControlConsumer(
            handler=self._handle_outreach_control,
            rabbitmq_config=control_config,
        )

    async def start(self) -> None:
        if not getattr(self.settings, "CHATBOT_ENABLED", True):
            self.logger.warning("Unified chatbot disabled via config; idling")
            await asyncio.Event().wait()
            return

        self.logger.info("Starting unified chatbot consumers")
        self._tasks = [
            asyncio.create_task(self.sample_consumer.start()),
            asyncio.create_task(self.outreach_consumer.start()),
            asyncio.create_task(self.control_consumer.start()),
        ]
        await asyncio.gather(*self._tasks)

    async def stop(self) -> None:
        self.logger.info("Stopping unified chatbot consumers")
        await self.sample_consumer.stop()
        await self.outreach_consumer.stop()
        await self.control_consumer.stop()
        await self._stop_all_outreach_tasks()
        for task in self._tasks:
            if not task.done():
                task.cancel()

    def _build_rabbitmq_config(
        self, *, prefix: str, defaults: Dict[str, Any]
    ) -> Dict[str, Any]:
        exchange_name = getattr(self.settings, f"{prefix}_EXCHANGE_NAME", None) or defaults.get(
            "exchange_name"
        )
        routing_key = getattr(self.settings, f"{prefix}_ROUTING_KEY", None) or defaults.get(
            "routing_key"
        )
        queue_name = getattr(self.settings, f"{prefix}_QUEUE_NAME", None) or defaults.get(
            "queue_name"
        )
        prefetch_count = getattr(
            self.settings, f"{prefix}_PREFETCH_COUNT", None
        )
        if prefetch_count is None:
            prefetch_count = defaults.get("prefetch_count")
        at_most_once = getattr(self.settings, f"{prefix}_AT_MOST_ONCE", None)
        if at_most_once is None:
            at_most_once = defaults.get("at_most_once")

        return {
            "exchange_name": exchange_name,
            "routing_key": routing_key,
            "queue_name": queue_name,
            "prefetch_count": prefetch_count,
            "at_most_once": at_most_once,
            "reconnect_delay": getattr(self.settings, "RABBITMQ_RECONNECT_DELAY", 5),
            "max_reconnect_attempts": getattr(self.settings, "RABBITMQ_MAX_RECONNECT_ATTEMPTS", 5),
        }

    async def _handle_outreach_control(
        self,
        action: str,
        task_id: str,
        queue_name: Optional[str],
        routing_key_prefix: Optional[str],
    ) -> None:
        async with self._control_lock:
            if action == "start":
                if task_id in self._outreach_task_consumers:
                    self.logger.info(
                        "Outreach consumer already running",
                        task_id=task_id,
                    )
                    return
                queue_name, routing_key_prefix = self._resolve_outreach_task_binding(
                    task_id, queue_name, routing_key_prefix
                )
                rabbitmq_config = self._build_outreach_task_config(
                    queue_name=queue_name,
                    routing_key_prefix=routing_key_prefix,
                )
                consumer = OutreachChatbotConsumer(rabbitmq_config=rabbitmq_config)
                task = asyncio.create_task(consumer.start())
                task.add_done_callback(self._consume_outreach_task_failure(task_id))
                self._outreach_task_consumers[task_id] = TaskConsumerState(
                    consumer=consumer,
                    task=task,
                )
                self.logger.info(
                    "Outreach consumer started",
                    task_id=task_id,
                    queue=queue_name,
                    routing_key=routing_key_prefix,
                )
            elif action == "end":
                await self._stop_outreach_task(task_id)
            else:
                self.logger.warning("Unknown outreach control action", action=action)

    def _consume_outreach_task_failure(self, task_id: str) -> Callable[[asyncio.Task], None]:
        def _callback(task: asyncio.Task) -> None:
            try:
                task.result()
            except asyncio.CancelledError:
                return
            except Exception:
                self.logger.warning(
                    "Outreach task consumer failed",
                    task_id=task_id,
                    exc_info=True,
                )
        return _callback

    def _resolve_outreach_task_binding(
        self,
        task_id: str,
        queue_name: Optional[str],
        routing_key_prefix: Optional[str],
    ) -> tuple[str, str]:
        if not queue_name:
            queue_prefix = str(
                getattr(self.settings, "RABBITMQ_OUTREACH_QUEUE_PREFIX", "") or ""
            ).strip()
            if not queue_prefix:
                queue_prefix = "chatbot.outreach.queue"
            queue_name = f"{queue_prefix}.{task_id}"
        if not routing_key_prefix:
            routing_key = str(
                getattr(self.settings, "RABBITMQ_OUTREACH_ROUTING_KEY", "") or ""
            ).strip()
            if not routing_key:
                routing_key = "chatbot.outreach.*"
            if routing_key.endswith(".*"):
                routing_key_prefix = routing_key[:-2]
            else:
                routing_key_prefix = routing_key
            routing_key_prefix = f"{routing_key_prefix}.{task_id}"
        return queue_name, routing_key_prefix

    def _build_outreach_task_config(
        self,
        *,
        queue_name: str,
        routing_key_prefix: str,
    ) -> Dict[str, Any]:
        base = self._build_rabbitmq_config(
            prefix="RABBITMQ_OUTREACH",
            defaults={
                "exchange_name": self.settings.RABBITMQ_EXCHANGE_NAME,
                "routing_key": "chatbot.outreach.*",
                "queue_name": "chatbot.outreach.queue.topic",
                "prefetch_count": getattr(self.settings, "RABBITMQ_PREFETCH_COUNT", 1),
                "at_most_once": getattr(self.settings, "RABBITMQ_AT_MOST_ONCE", False),
            },
        )
        base.update(
            {
                "routing_key": f"{routing_key_prefix}.*",
                "queue_name": queue_name,
                "queue_arguments": {"x-expires": OUTREACH_QUEUE_EXPIRES_MS},
                "queue_durable": False,
                "queue_auto_delete": True,
                "queue_exclusive": False,
                "dlq_arguments": {"x-expires": OUTREACH_QUEUE_EXPIRES_MS},
                "dlq_durable": False,
                "dlq_auto_delete": True,
            }
        )
        return base

    async def _stop_outreach_task(self, task_id: str) -> None:
        state = self._outreach_task_consumers.pop(task_id, None)
        if not state:
            self.logger.info("Outreach consumer already stopped", task_id=task_id)
            return
        try:
            idle_seconds = float(
                getattr(self.settings, "OUTREACH_CHATBOT_DRAIN_IDLE_SECONDS", 3) or 3
            )
            timeout_seconds = float(
                getattr(self.settings, "OUTREACH_CHATBOT_DRAIN_TIMEOUT_SECONDS", 120) or 120
            )
            await state.consumer.drain_and_stop(
                idle_seconds=idle_seconds,
                timeout_seconds=timeout_seconds,
            )
        finally:
            if not state.task.done():
                state.task.cancel()
        self.logger.info("Outreach consumer stopped", task_id=task_id)

    async def _stop_all_outreach_tasks(self) -> None:
        for task_id in list(self._outreach_task_consumers.keys()):
            await self._stop_outreach_task(task_id)
