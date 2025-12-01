"""
线程化的爬虫任务执行器
"""
from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, Callable, Dict, List, Optional, Set

from crawler.creator_full_crawler import CreatorFullCrawler, CrawlerCancelledError

logger = logging.getLogger(__name__)


@dataclass
class CrawlerTaskResult:
    """封装爬虫返回结果。"""

    success: bool
    new_creators: int = 0
    total_creators: int = 0
    output_files: List[str] = field(default_factory=list)
    message: str = ""
    cancelled: bool = False
    latest_creator: Optional[str] = None


class CrawlerTaskWorker:
    """单个爬虫任务的执行器，负责准备环境并调用具体的爬虫类。"""

    def __init__(
        self,
        task_id: str,
        task_dir: Path,
        task_config: Dict,
        max_creators: int,
        target_new: int,
        account_info: Optional[Dict] = None,
        cancel_event: Optional[Event] = None,
        progress_callback: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self.task_id = task_id
        self.task_dir = Path(task_dir)
        self.task_config = task_config
        self.max_creators = max(1, int(max_creators))
        self.target_new = max(1, int(target_new))
        self.account_info = account_info
        self.log_path = str(self.task_dir / "crawler.log")
        self.cancel_event = cancel_event
        self.progress_callback = progress_callback

    # ------------------------------------------------------------------
    def run(self) -> CrawlerTaskResult:
        """执行爬虫任务，并返回执行结果。"""
        try:
            if self.cancel_event and self.cancel_event.is_set():
                logger.info("任务 %s 在启动前被取消", self.task_id)
                return CrawlerTaskResult(
                    success=False,
                    message="任务已取消",
                    output_files=self._collect_outputs(),
                    cancelled=True,
                )

            self.task_dir.mkdir(parents=True, exist_ok=True)
            self.task_config["task_id"] = self.task_id
            self.task_config.setdefault("task_name", self.task_config.get("task_name"))
            self.task_config.setdefault("campaign_id", self.task_config.get("campaign_id"))
            self.task_config.setdefault("campaign_name", self.task_config.get("campaign_name"))
            self.task_config.setdefault("run_at_time", self.task_config.get("run_at_time"))
            self.task_config["max_creators"] = self.max_creators
            self.task_config["target_new_creators"] = self.target_new
            self._write_config_files()

            total_target = max(1, int(self.target_new))
            per_batch_limit = max(1, min(40, self.max_creators))
            min_batch_threshold = 5
            max_batches = 10

            total_new = 0
            total_scanned = 0
            latest_creator = None
            aggregated_success = True
            last_batch_new = 0
            cancelled = False
            shared_seen_creators: Set[str] = set()
            shared_skipped_creators: Set[str] = set()

            for batch_idx in range(max_batches):
                if self.cancel_event and self.cancel_event.is_set():
                    logger.info("任务 %s 捕获到取消信号，退出批处理循环", self.task_id)
                    cancelled = True
                    break

                remaining = total_target - total_new
                if remaining <= 0 and batch_idx > 0 and last_batch_new >= min_batch_threshold:
                    break

                current_target = per_batch_limit if remaining <= 0 else min(per_batch_limit, max(remaining, 1))
                base_total = total_new

                def progress_proxy(progress: Any) -> None:
                    if not self.progress_callback:
                        return
                    scaled = progress
                    if isinstance(progress, dict):
                        scaled = progress.copy()
                        if "new_creators" in progress:
                            try:
                                scaled["new_creators"] = base_total + int(progress["new_creators"])
                            except (TypeError, ValueError):
                                scaled["new_creators"] = base_total
                    self.progress_callback(scaled)

                crawler = CreatorFullCrawler(
                    search_strategy=self.task_config.get("search_strategy"),
                    task_id=self.task_id,
                    task_dir=self.task_dir,
                    max_creators_to_load=self.max_creators,
                    account_info=self.account_info,
                    cancel_event=self.cancel_event,
                    task_metadata=self.task_config,
                    shared_record_callback=progress_proxy,
                    shared_seen_creators=shared_seen_creators,
                    shared_skipped_creators=shared_skipped_creators,
                )
                crawler.target_new_count = current_target
                crawler.max_creators = self.max_creators

                logger.info(
                    "任务 %s 启动第 %s/%s 批爬虫，批次目标=%s，已累计新增=%s/%s",
                    self.task_id,
                    batch_idx + 1,
                    max_batches,
                    current_target,
                    total_new,
                    total_target,
                )

                batch_success = crawler.run(max_creators=self.max_creators)
                restart_requested = getattr(crawler, "restart_requested", False)
                restart_reason = getattr(crawler, "restart_reason", "")
                if self.cancel_event and self.cancel_event.is_set():
                    logger.info("任务 %s 在批次 %s 后收到取消信号，准备退出", self.task_id, batch_idx + 1)
                    cancelled = True
                    latest_creator = getattr(crawler, "latest_creator_name", latest_creator)
                    total_new += int(getattr(crawler, "new_processed_count", 0))
                    total_scanned += int(getattr(crawler, "creator_counter", 0))
                    break
                batch_new = int(getattr(crawler, "new_processed_count", 0))
                total_new += batch_new
                last_batch_new = batch_new
                total_scanned += int(getattr(crawler, "creator_counter", 0))
                latest_creator = getattr(crawler, "latest_creator_name", latest_creator)
                aggregated_success = aggregated_success and bool(batch_success)
                if restart_requested:
                    logger.info(
                        "任务 %s 第 %s 批触发浏览器重启请求：%s",
                        self.task_id,
                        batch_idx + 1,
                        restart_reason or "阈值触发",
                    )

                logger.info(
                    "任务 %s 第 %s 批执行完成，批次新增=%s，累计新增=%s/%s",
                    self.task_id,
                    batch_idx + 1,
                    batch_new,
                    total_new,
                    total_target,
                )

                if self.progress_callback:
                    self.progress_callback({
                        "latest_creator": latest_creator,
                        "new_creators": total_new,
                    })

                if crawler.was_cancelled or (self.cancel_event and self.cancel_event.is_set()):
                    cancelled = True
                    break

                if restart_requested:
                    logger.info(
                        "任务 %s 按策略拆分批次，准备重新启动浏览器以继续执行",
                        self.task_id,
                    )
                    if total_new >= total_target:
                        logger.info("任务 %s 已满足目标新增数量，结束批次循环", self.task_id)
                        break
                    if batch_idx == max_batches - 1:
                        logger.info("任务 %s 已达到最大批次数，无法继续追加批次", self.task_id)
                        break
                    continue

                if batch_new < min_batch_threshold:
                    logger.info(
                        "任务 %s 第 %s 批仅新增 %s 个达人，停止后续批次",
                        self.task_id,
                        batch_idx + 1,
                        batch_new,
                    )
                    break

                if total_new >= total_target:
                    break

                if batch_idx == max_batches - 1:
                    break

            output_files = self._collect_outputs()

            if cancelled:
                return CrawlerTaskResult(
                    success=False,
                    new_creators=total_new,
                    total_creators=total_scanned,
                    output_files=output_files,
                    message="任务已取消",
                    cancelled=True,
                    latest_creator=latest_creator,
                )

                
            if not aggregated_success:
                return CrawlerTaskResult(
                    success=False,
                    new_creators=total_new,
                    total_creators=total_scanned,
                    output_files=output_files,
                    message="任务执行失败，请检查日志",
                    latest_creator=latest_creator,
                )

            message = "任务执行完成" if total_new >= total_target else "任务执行完成（未达到目标上限）"
            return CrawlerTaskResult(
                success=True,
                new_creators=total_new,
                total_creators=total_scanned,
                output_files=output_files,
                message=message,
                latest_creator=latest_creator,
            )

        except CrawlerCancelledError:
            logger.info("任务 %s 捕获到取消异常", self.task_id)
            return CrawlerTaskResult(
                success=False,
                message="任务已取消",
                output_files=self._collect_outputs(),
                cancelled=True,
                latest_creator=None,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("任务 %s 执行异常: %s", self.task_id, exc)
            return CrawlerTaskResult(
                success=False,
                message=str(exc),
                output_files=self._collect_outputs(),
                latest_creator=None,
            )

    # ------------------------------------------------------------------
    def _write_config_files(self) -> None:
        """写入爬虫所需的配置文件，供 CreatorFullCrawler 读取。"""
        dify_path = self.task_dir / "dify_out.txt"
        request_snapshot = self.task_dir / "request.json"

        config_to_dump = copy.deepcopy(self.task_config)
        try:
            only_first_raw = ((config_to_dump.get("brand") or {}).get("only_first"))
            only_first = int(only_first_raw) if only_first_raw is not None else None
        except (ValueError, TypeError):
            only_first = None

        if only_first in (0, 2):
            email_later = config_to_dump.get("email_later")
            subject = (email_later or {}).get("subject", "")
            body = (email_later or {}).get("email_body", "")
            if not (str(subject).strip() or str(body).strip()):
                config_to_dump["email_later"] = config_to_dump.get("email_first", {}).copy()

        with dify_path.open("w", encoding="utf-8") as fp:
            json.dump(config_to_dump, fp, ensure_ascii=False, indent=2)

        # 额外保存一次完整请求，便于排查问题
        snapshot_payload = {
            "task_id": self.task_id,
            "max_creators": self.max_creators,
            "target_new": self.target_new,
            "config": self.task_config,
        }
        with request_snapshot.open("w", encoding="utf-8") as fp:
            json.dump(snapshot_payload, fp, ensure_ascii=False, indent=2)

    def _collect_outputs(self) -> List[str]:
        """收集任务目录下的关键输出文件。"""
        if not self.task_dir.exists():
            return []

        patterns = ("*.xlsx", "*.csv", "*.json")
        files: List[str] = []
        for pattern in patterns:
            for file_path in self.task_dir.rglob(pattern):
                if file_path.is_file():
                    files.append(str(file_path))
        return sorted(set(files))
