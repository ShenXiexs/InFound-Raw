import asyncio
import json
from typing import Optional
from urllib.parse import quote_plus

import aio_pika
from aio_pika import ExchangeType

from common.core.config import get_settings
from common.core.exceptions import MessageProcessingError, PlaywrightError
from common.core.logger import get_logger
from common.mq.connection import RabbitMQConnection
from common.mq.consumer_base import ConsumerBase

from .services.chatbot_dispatcher_service import (
    ChatbotDispatchTask,
    ChatbotDispatcherService,
)


class CrawlerConsumer(ConsumerBase):
    """Chatbot dispatcher consumer (sender only; supports batch tasks)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        amqp_url = (
            f"amqp://{quote_plus(self.settings.RABBITMQ_USERNAME)}:"
            f"{quote_plus(self.settings.RABBITMQ_PASSWORD)}@"
            f"{self.settings.RABBITMQ_HOST}:{self.settings.RABBITMQ_PORT}/"
            f"{quote_plus(self.settings.RABBITMQ_VHOST)}"
        )
        # Use topic exchange to match batched messages from inner API.
        exchange_type = ExchangeType.TOPIC
        rabbitmq_conn = RabbitMQConnection(
            url=amqp_url,
            exchange_name=self.settings.RABBITMQ_EXCHANGE_NAME,
            routing_key=self.settings.RABBITMQ_ROUTING_KEY,
            queue_name=self.settings.RABBITMQ_QUEUE_NAME,
            at_most_once=getattr(self.settings, "RABBITMQ_AT_MOST_ONCE", False),
            prefetch_count=self.settings.RABBITMQ_PREFETCH_COUNT,
            reconnect_delay=self.settings.RABBITMQ_RECONNECT_DELAY,
            max_reconnect_attempts=self.settings.RABBITMQ_MAX_RECONNECT_ATTEMPTS,
            exchange_type=exchange_type,
        )
        super().__init__(rabbitmq_conn)
        self.logger = get_logger().bind(consumer="sample_chatbot")
        self._idle_event: Optional[asyncio.Event] = None
        self.dispatcher = ChatbotDispatcherService()

    async def start(self) -> None:
        if not getattr(self.settings, "CHATBOT_ENABLED", True):
            self.logger.warning("Sample chatbot disabled via config; idling")
            self._idle_event = asyncio.Event()
            await self._idle_event.wait()
            return

        # Prewarm a resident Playwright session (similar to sample crawler).
        if getattr(self.settings, "CHATBOT_PREWARM_BROWSER", True):
            asyncio.create_task(self.dispatcher.prewarm())

        await super().start()

    async def stop(self) -> None:
        await self.dispatcher.close()
        if not getattr(self.settings, "CHATBOT_ENABLED", True) and self._idle_event:
            self._idle_event.set()
            return
        await super().stop()

    async def process_message_body(self, message_id: str, body: object) -> None:
        """
        Handle MQ message payloads:
        - batch: { "taskId": "...", "tasks": [ { "messages": [...] }, ... ] }
        - single: { "messages": [...] }
        - array: [ { "messages": [...] }, ... ]
        """
        import uuid

        if isinstance(body, list):
            items = body
            is_batch = True
            batch_task_id = str(message_id)
            base_payload = {}
        elif isinstance(body, dict):
            tasks = body.get("tasks")
            is_batch = isinstance(tasks, list)
            batch_task_id = str(body.get("taskId") or message_id)
            base_payload = {key: value for key, value in body.items() if key != "tasks"}
            items = tasks if is_batch else [body]
        else:
            self.logger.warning("Unsupported message body type", message_id=message_id)
            return
        if not items:
            self.logger.warning("Empty tasks array in message", batch_task_id=batch_task_id)
            return

        self.logger.info(
            "Processing chat tasks",
            batch_task_id=batch_task_id,
            task_count=len(items),
            is_batch=is_batch,
        )

        success_count = 0
        error_count = 0
        for idx, raw in enumerate(items, start=1):
            if not isinstance(raw, dict):
                error_count += 1
                await self._publish_to_dead_letter_strict(
                    json.dumps(raw, ensure_ascii=False).encode("utf-8"),
                    message_id=None,
                    reason=f"task payload is not an object (index={idx})",
                )
                continue

            payload = dict(base_payload)
            payload.update(raw)
            if not payload.get("taskId"):
                payload["taskId"] = str(uuid.uuid4()).upper()

            try:
                task = ChatbotDispatchTask.from_payload(payload)
                await self.dispatcher.dispatch(task)
                success_count += 1
                self.logger.info(
                    "Chat task dispatched",
                    batch_task_id=batch_task_id,
                    task_index=idx,
                    task_id=task.task_id,
                    sample_id=task.sample_id,
                    message_count=len(task.messages or []),
                )
            except PlaywrightError as exc:
                error_count += 1
                self.logger.error(
                    "Chat task dispatch failed; resetting browser and dropping batch",
                    batch_task_id=batch_task_id,
                    task_index=idx,
                    task_id=payload.get("taskId"),
                    message_count=len(payload.get("messages") or []),
                    exc_info=True,
                )
                try:
                    await self.dispatcher.close()
                except Exception:
                    self.logger.warning(
                        "Failed to close chatbot browser after dispatch failure",
                        exc_info=True,
                    )
                raise MessageProcessingError(
                    "Playwright session reset; drop current message"
                ) from exc
            except Exception as exc:
                error_count += 1
                await self._publish_to_dead_letter_strict(
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    message_id=str(payload.get("taskId") or "") or None,
                    reason=f"dispatch failed (index={idx}): {exc}",
                )
                self.logger.error(
                    "Chat task dispatch failed",
                    batch_task_id=batch_task_id,
                    task_index=idx,
                    task_id=payload.get("taskId"),
                    message_count=len(payload.get("messages") or []),
                    exc_info=True,
                )

        self.logger.info(
            "Chat tasks processed",
            batch_task_id=batch_task_id,
            success_count=success_count,
            error_count=error_count,
            total_count=len(items),
            is_batch=is_batch,
        )

    async def _publish_to_dead_letter_strict(
        self,
        body: bytes,
        *,
        message_id: Optional[str],
        reason: str,
    ) -> None:
        dlx_exchange = getattr(self.rabbitmq_conn, "dlx_exchange", None)
        if not dlx_exchange:
            raise MessageProcessingError("Dead-letter exchange is not available")

        headers = {"x-error": reason}
        if message_id:
            headers["x-original-message-id"] = message_id

        try:
            await dlx_exchange.publish(
                aio_pika.Message(
                    body=body,
                    message_id=message_id,
                    headers=headers,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                ),
                routing_key=self.rabbitmq_conn.dl_routing_key,
            )
        except Exception as exc:
            raise MessageProcessingError(f"Failed to publish to DLQ: {exc}") from exc
