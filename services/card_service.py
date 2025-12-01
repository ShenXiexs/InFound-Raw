from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Dict, Optional, Tuple, List
from uuid import uuid4

from product_card.creator_product import generate_card_send_list
from product_card.chat_card import (
    CardSender,
    select_account_for_region,
    DEFAULT_ACCOUNTS_JSON,
)
from schemas.card import CardTaskStatus

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
BASE_CARD_DIR = ROOT_DIR / "data" / "card"
TASK_ROOT = BASE_CARD_DIR / "tasks"
DEFAULT_CREATOR_FILENAME = "creator.xlsx"
DEFAULT_PRODUCT_FILENAME = "product.xlsx"


def _now() -> datetime:
    return datetime.utcnow()


@dataclass
class CardTaskRecord:
    task_id: str
    task_dir: Path
    creator_file: Path
    product_file: Path
    generate_only: bool
    headless: bool
    verify_delivery: bool
    manual_login_timeout: int
    created_by: str
    region: str = "MX"
    account_name: Optional[str] = None
    status: str = "pending"
    message: Optional[str] = None
    created_at: datetime = field(default_factory=_now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    output_json: Optional[Path] = None
    record_count: int = 0
    future: Optional[Future] = None
    output_files: List[str] = field(default_factory=list)

    def to_status(self) -> CardTaskStatus:
        return CardTaskStatus(
            task_id=self.task_id,
            status=self.status,
            task_type="Card",
            message=self.message,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            creator_file=str(self.creator_file),
            product_file=str(self.product_file),
            output_json=str(self.output_json) if self.output_json else None,
            output_files=self.output_files,
            task_dir=str(self.task_dir),
            record_count=self.record_count,
            generate_only=self.generate_only,
            headless=self.headless,
            verify_delivery=self.verify_delivery,
            manual_login_timeout=self.manual_login_timeout,
            created_by=self.created_by,
            region=self.region,
            account_name=self.account_name,
        )


class CardService:
    """商品卡发送后台服务"""

    def __init__(self, max_workers: int = 1) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="card-task")
        self._tasks: Dict[str, CardTaskRecord] = {}
        self._lock = Lock()
        TASK_ROOT.mkdir(parents=True, exist_ok=True)
        BASE_CARD_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("CardService 初始化完成 (max_workers=%s)", max_workers)

    def submit_task(
        self,
        *,
        creator_bytes: bytes,
        creator_filename: str,
        product_bytes: bytes,
        product_filename: str,
        headless: bool,
        verify_delivery: bool,
        manual_login_timeout: int,
        generate_only: bool,
        created_by: str,
        region: str,
        account_name: Optional[str],
    ) -> Tuple[str, CardTaskStatus]:
        task_id = datetime.utcnow().strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:6]
        task_dir = TASK_ROOT / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        creator_path = task_dir / (creator_filename or DEFAULT_CREATOR_FILENAME)
        product_path = task_dir / (product_filename or DEFAULT_PRODUCT_FILENAME)

        creator_path.write_bytes(creator_bytes)
        product_path.write_bytes(product_bytes)

        record = CardTaskRecord(
            task_id=task_id,
            task_dir=task_dir,
            creator_file=creator_path,
            product_file=product_path,
            generate_only=generate_only,
            headless=headless,
            verify_delivery=verify_delivery,
            manual_login_timeout=manual_login_timeout,
            created_by=created_by,
            region=(region or "MX").upper(),
            account_name=account_name,
        )

        with self._lock:
            self._tasks[task_id] = record
            record.future = self._executor.submit(self._execute_task, record)

        logger.info("商品卡任务 %s 已提交 (generate_only=%s)", task_id, generate_only)
        return task_id, record.to_status()

    def list_tasks(self) -> List[CardTaskStatus]:
        with self._lock:
            records = list(self._tasks.values())
        records.sort(key=lambda r: r.created_at, reverse=True)
        return [record.to_status() for record in records]

    def get_task(self, task_id: str) -> Optional[CardTaskStatus]:
        with self._lock:
            record = self._tasks.get(task_id)
        return record.to_status() if record else None

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                return False
            if record.status not in {"pending"}:
                return False
            if record.future and record.future.cancel():
                record.status = "cancelled"
                record.finished_at = _now()
                record.message = "任务已在执行前取消"
                return True
            return False

    def _execute_task(self, record: CardTaskRecord) -> None:
        logger.info("开始执行商品卡任务 %s", record.task_id)
        record.started_at = _now()
        record.status = "running"

        try:
            result = generate_card_send_list(
                creator_file=record.creator_file,
                product_file=record.product_file,
                output_dir=record.task_dir,
                update_latest=True,
            )
            record.output_json = Path(result["output_file"])
            record.record_count = int(result["record_count"])
            record.output_files = (
                [str(record.output_json)] if record.output_json else []
            )
            logger.info(
                "任务 %s 成功生成 JSON，共 %s 条记录",
                record.task_id,
                record.record_count,
            )

            if record.generate_only:
                record.status = "completed"
                record.message = "仅生成 JSON，未执行发送"
                return

            account_info = select_account_for_region(
                record.region,
                record.account_name,
                DEFAULT_ACCOUNTS_JSON,
            )
            if not account_info:
                raise RuntimeError(
                    f"没有找到区域 {record.region} 的发送账号，请检查 config/accounts.json"
                )

            sender = CardSender(
                account_info=account_info,
                region=record.region,
                headless=record.headless,
                manual_login_timeout=record.manual_login_timeout,
                verify_delivery=record.verify_delivery,
                card_data_path=record.output_json,
            )
            success = sender.run()
            if success:
                record.status = "completed"
                record.message = "商品卡发送完成"
            else:
                record.status = "failed"
                record.message = "商品卡发送未全部成功，请检查日志"
        except Exception as exc:
            logger.exception("商品卡任务 %s 执行失败: %s", record.task_id, exc)
            record.status = "failed"
            record.message = str(exc)
        finally:
            record.finished_at = _now()
            logger.info(
                "任务 %s 结束，状态=%s，用时 %.1fs",
                record.task_id,
                record.status,
                (record.finished_at - record.started_at).total_seconds()
                if record.started_at and record.finished_at
                else -1,
            )


_card_service: Optional[CardService] = None
_service_lock = Lock()


def get_card_service() -> CardService:
    global _card_service
    if _card_service is None:
        with _service_lock:
            if _card_service is None:
                _card_service = CardService()
    return _card_service
