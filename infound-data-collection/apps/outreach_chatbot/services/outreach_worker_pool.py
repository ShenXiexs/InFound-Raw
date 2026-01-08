from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, List, Optional

from common.core.exceptions import PlaywrightError
from common.core.logger import get_logger

from .outreach_dispatcher_service import OutreachChatbotDispatcherService, OutreachChatbotTask

logger = get_logger().bind(component="outreach_chatbot_pool")


@dataclass
class _Worker:
    dispatcher: OutreachChatbotDispatcherService
    account_name: Optional[str]


class OutreachChatbotWorkerPool:
    def __init__(
        self,
        *,
        worker_count: int,
        account_names: Iterable[Optional[str]],
    ) -> None:
        self.worker_count = max(int(worker_count or 1), 1)
        self.account_names: List[Optional[str]] = list(account_names) or [None]
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: List[_Worker] = []
        self._worker_tasks: List[asyncio.Task] = []
        self._inflight = 0
        self._closed = False

    async def start(self) -> None:
        if self._workers:
            return
        for idx in range(self.worker_count):
            account_name = self.account_names[idx % len(self.account_names)]
            dispatcher = OutreachChatbotDispatcherService(account_name=account_name)
            worker = _Worker(dispatcher=dispatcher, account_name=account_name)
            self._workers.append(worker)
            self._worker_tasks.append(asyncio.create_task(self._worker_loop(worker)))

    async def submit(self, task: OutreachChatbotTask) -> asyncio.Future:
        if self._closed:
            raise RuntimeError("Worker pool is closed")
        if not self._workers:
            await self.start()
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        await self._queue.put((task, fut))
        return fut

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for _ in self._workers:
            await self._queue.put(None)
        for task in self._worker_tasks:
            try:
                await task
            except Exception:
                pass
        for worker in self._workers:
            try:
                await worker.dispatcher.close()
            except Exception:
                logger.warning("Failed to close dispatcher", exc_info=True)

    def pending_counts(self) -> tuple[int, int]:
        return self._queue.qsize(), self._inflight

    async def wait_idle(
        self,
        *,
        idle_seconds: float = 3.0,
        timeout_seconds: float = 120.0,
    ) -> bool:
        deadline = asyncio.get_running_loop().time() + max(timeout_seconds, 0)
        idle_since = None
        while asyncio.get_running_loop().time() < deadline:
            queued, inflight = self.pending_counts()
            if queued == 0 and inflight == 0:
                if idle_since is None:
                    idle_since = asyncio.get_running_loop().time()
                if asyncio.get_running_loop().time() - idle_since >= idle_seconds:
                    return True
            else:
                idle_since = None
            await asyncio.sleep(0.5)
        return False

    async def _worker_loop(self, worker: _Worker) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            task, fut = item
            try:
                self._inflight += 1
                await worker.dispatcher.dispatch(task)
                if not fut.cancelled():
                    fut.set_result(True)
            except PlaywrightError as exc:
                try:
                    await worker.dispatcher.close()
                except Exception:
                    logger.warning("Failed to reset dispatcher", exc_info=True)
                if not fut.cancelled():
                    fut.set_exception(exc)
            except Exception as exc:
                if not fut.cancelled():
                    fut.set_exception(exc)
            finally:
                self._inflight = max(self._inflight - 1, 0)
                self._queue.task_done()
