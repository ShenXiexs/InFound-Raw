import asyncio
from typing import Any, Dict, Set
from urllib.parse import quote_plus

from common.core.config import get_settings
from common.core.logger import get_logger
from common.mq.connection import RabbitMQConnection
from common.mq.consumer_base import ConsumerBase

from .services.creator_crawler_service import CreatorCrawlerService


class CrawlerConsumer(ConsumerBase):
    """Creator crawler consumer that spawns one browser per incoming task."""

    def __init__(self) -> None:
        self.settings = get_settings()
        amqp_url = (
            f"amqp://{quote_plus(self.settings.RABBITMQ_USERNAME)}:"
            f"{quote_plus(self.settings.RABBITMQ_PASSWORD)}@"
            f"{self.settings.RABBITMQ_HOST}:{self.settings.RABBITMQ_PORT}/"
            f"{quote_plus(self.settings.RABBITMQ_VHOST)}"
        )
        rabbitmq_conn = RabbitMQConnection(
            url=amqp_url,
            exchange_name=self.settings.RABBITMQ_EXCHANGE_NAME,
            routing_key=self.settings.RABBITMQ_ROUTING_KEY,
            queue_name=self.settings.RABBITMQ_QUEUE_NAME,
            at_most_once=getattr(self.settings, "RABBITMQ_AT_MOST_ONCE", False),
            prefetch_count=self.settings.RABBITMQ_PREFETCH_COUNT,
            reconnect_delay=self.settings.RABBITMQ_RECONNECT_DELAY,
            max_reconnect_attempts=self.settings.RABBITMQ_MAX_RECONNECT_ATTEMPTS,
        )
        super().__init__(rabbitmq_conn)
        self.logger = get_logger().bind(consumer="portal_tiktok_creator_crawler")
        self._active_tasks: Set[asyncio.Task] = set()

    @staticmethod
    def _consume_background_task(task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger = get_logger(__name__)
            logger.warning("Background task failed", exc_info=True)

    async def start(self) -> None:
        await super().start()

    async def stop(self) -> None:
        for task in list(self._active_tasks):
            task.cancel()
        await super().stop()

    async def process_message_body(self, message_id: str, body: Dict[str, Any]) -> None:
        if not isinstance(body, dict):
            self.logger.warning("Unsupported message body type", message_id=message_id)
            return

        task = asyncio.create_task(self._run_single_task(message_id, body))
        task.add_done_callback(self._consume_background_task)
        task.add_done_callback(lambda done: self._active_tasks.discard(done))
        self._active_tasks.add(task)

    async def _run_single_task(self, message_id: str, body: Dict[str, Any]) -> None:
        service = CreatorCrawlerService()
        try:
            creators = await service.run_from_payload(body)
            self.logger.info(
                "Creator search completed",
                message_id=message_id,
                creator_count=len(creators),
            )
        except Exception as exc:
            self.logger.error(
                "Creator crawl failed",
                message_id=message_id,
                error=str(exc),
                exc_info=True,
            )
        finally:
            try:
                await service.close()
            except Exception:
                self.logger.warning("Failed to close crawler service", exc_info=True)
