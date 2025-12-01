"""
持久化存储建联任务，供 API 重启后继续展示历史任务。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select, inspect, text
from sqlalchemy.exc import NoSuchTableError

from database.db import get_session, engine, now_beijing
from database.models import OutreachTask
from schemas.crawler import CrawlerTaskStatus

_OUTREACH_SCHEMA_CHECKED = False


def ensure_outreach_task_schema(force_refresh: bool = False) -> None:
    """确保 outreach_task 表包含最新字段。"""
    global _OUTREACH_SCHEMA_CHECKED
    if _OUTREACH_SCHEMA_CHECKED and not force_refresh:
        return

    inspector = inspect(engine)
    try:
        columns = {col["name"] for col in inspector.get_columns("outreach_task")}
    except NoSuchTableError:
        # 如果表不存在则直接按照模型创建
        OutreachTask.__table__.create(bind=engine, checkfirst=True)
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("outreach_task")}

    alters: List[str] = []

    def add_column(name: str, ddl: str) -> None:
        if name not in columns:
            alters.append(ddl)

    add_column("task_type", "ALTER TABLE outreach_task ADD COLUMN task_type VARCHAR(32)")
    add_column("status", "ALTER TABLE outreach_task ADD COLUMN status VARCHAR(32)")
    add_column("message", "ALTER TABLE outreach_task ADD COLUMN message TEXT")
    add_column("created_by", "ALTER TABLE outreach_task ADD COLUMN created_by VARCHAR(255)")
    add_column("account_email", "ALTER TABLE outreach_task ADD COLUMN account_email VARCHAR(255)")
    add_column("log_path", "ALTER TABLE outreach_task ADD COLUMN log_path TEXT")
    add_column("output_files", "ALTER TABLE outreach_task ADD COLUMN output_files TEXT")
    add_column("total_creators", "ALTER TABLE outreach_task ADD COLUMN total_creators INTEGER")
    add_column("payload_json", "ALTER TABLE outreach_task ADD COLUMN payload_json TEXT")
    add_column("started_at", "ALTER TABLE outreach_task ADD COLUMN started_at DATETIME")
    add_column("finished_at", "ALTER TABLE outreach_task ADD COLUMN finished_at DATETIME")

    if alters:
        with engine.begin() as conn:
            for stmt in alters:
                conn.execute(text(stmt))

    _OUTREACH_SCHEMA_CHECKED = True


ensure_outreach_task_schema()


def _task_to_snapshot(task: OutreachTask) -> Dict[str, Any]:
    """将 ORM 记录转换为存储快照（用于恢复未执行任务）。"""
    payload = _loads_json(task.payload_json, None)
    output_files = _loads_json(task.output_files, [])
    snapshot: Dict[str, Any] = {
        "task_id": task.task_id,
        "task_name": task.task_name,
        "campaign_id": task.campaign_id,
        "campaign_name": task.campaign_name,
        "product_id": task.product_id,
        "product_name": task.product_name,
        "region": task.region,
        "brand": task.brand,
        "only_first": task.only_first,
        "task_type": task.task_type,
        "status": task.status,
        "message": task.message,
        "created_by": task.created_by,
        "account_email": task.account_email,
        "search_keywords": task.search_keywords,
        "product_category": task.product_category,
        "fans_age_range": task.fans_age_range,
        "fans_gender": task.fans_gender,
        "min_fans": task.min_fans,
        "content_type": task.content_type,
        "gmv": task.gmv,
        "sales": task.sales,
        "min_GMV": task.min_GMV,
        "max_GMV": task.max_GMV,
        "avg_views": task.avg_views,
        "min_engagement_rate": task.min_engagement_rate,
        "email_first_subject": task.email_first_subject,
        "email_first_body": task.email_first_body,
        "email_later_subject": task.email_later_subject,
        "email_later_body": task.email_later_body,
        "target_new_creators": task.target_new_creators,
        "max_creators": task.max_creators,
        "run_at_time": _parse_datetime(task.run_at_time),
        "run_end_time": _parse_datetime(task.run_end_time),
        "run_time": task.run_time,
        "task_directory": task.task_directory,
        "log_path": task.log_path,
        "connect_creator": task.connect_creator,
        "new_creators": task.new_creators,
        "total_creators": task.total_creators,
        "submitted_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "payload": payload,
        "output_files": output_files,
    }
    return snapshot


def _isoformat(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    try:
        return datetime.fromisoformat(str(dt)).isoformat()
    except ValueError:
        return str(dt)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _loads_json(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _task_to_status(task: OutreachTask) -> CrawlerTaskStatus:
    payload = _loads_json(task.payload_json, None)
    output_files = _loads_json(task.output_files, [])
    run_at_time = _parse_datetime(task.run_at_time)
    run_end_time = _parse_datetime(task.run_end_time)
    return CrawlerTaskStatus(
        task_id=task.task_id,
        task_type=task.task_type or "Connect",
        status=task.status or "pending",
        message=task.message,
        submitted_at=task.created_at,
        started_at=_parse_datetime(task.started_at),
        finished_at=_parse_datetime(task.finished_at),
        user=task.created_by,
        task_name=task.task_name,
        campaign_id=task.campaign_id,
        campaign_name=task.campaign_name,
        region=task.region,
        brand_name=task.brand,
        account_email=task.account_email,
        new_creators=task.new_creators,
        total_creators=task.total_creators,
        task_dir=task.task_directory,
        log_path=task.log_path,
        product_name=task.product_name,
        product_id=task.product_id,
        connect_creator=task.connect_creator,
        run_time=task.run_time,
        payload=payload,
        output_files=output_files,
        max_creators=task.max_creators,
        target_new_creators=task.target_new_creators,
        run_at_time=run_at_time,
        run_end_time=run_end_time,
    )


def persist_task_snapshot(snapshot: Dict[str, Any]) -> None:
    """根据任务快照写入/更新 outreach_task 表。"""
    task_id = snapshot.get("task_id")
    if not task_id:
        return

    payload = snapshot.get("payload")
    output_files = snapshot.get("output_files") or []

    with get_session() as db:
        task = db.get(OutreachTask, task_id)
        if task is None:
            task = OutreachTask(task_id=task_id)
            db.add(task)

        task.task_name = snapshot.get("task_name")
        task.campaign_id = snapshot.get("campaign_id")
        task.campaign_name = snapshot.get("campaign_name")
        task.product_id = snapshot.get("product_id")
        task.product_name = snapshot.get("product_name")
        task.region = snapshot.get("region")
        task.brand = snapshot.get("brand")
        task.only_first = snapshot.get("only_first")
        task.task_type = snapshot.get("task_type") or "Connect"
        task.status = snapshot.get("status") or task.status or "pending"
        task.message = snapshot.get("message")
        task.created_by = snapshot.get("created_by")
        task.account_email = snapshot.get("account_email")

        task.search_keywords = snapshot.get("search_keywords")
        task.product_category = snapshot.get("product_category")
        task.fans_age_range = snapshot.get("fans_age_range")
        task.fans_gender = snapshot.get("fans_gender")
        task.min_fans = snapshot.get("min_fans")
        task.content_type = snapshot.get("content_type")
        task.gmv = snapshot.get("gmv")
        task.sales = snapshot.get("sales")
        task.min_GMV = snapshot.get("min_GMV")
        task.max_GMV = snapshot.get("max_GMV")
        task.avg_views = snapshot.get("avg_views")
        task.min_engagement_rate = snapshot.get("min_engagement_rate")
        task.email_first_subject = snapshot.get("email_first_subject")
        task.email_first_body = snapshot.get("email_first_body")
        task.email_later_subject = snapshot.get("email_later_subject")
        task.email_later_body = snapshot.get("email_later_body")
        task.target_new_creators = snapshot.get("target_new_creators")
        task.max_creators = snapshot.get("max_creators")
        task.run_at_time = _isoformat(snapshot.get("run_at_time"))
        task.run_end_time = _isoformat(snapshot.get("run_end_time"))
        task.run_time = snapshot.get("run_time")
        task.task_directory = snapshot.get("task_directory")
        task.log_path = snapshot.get("log_path")

        task.connect_creator = snapshot.get("connect_creator")
        task.new_creators = snapshot.get("new_creators")
        task.total_creators = snapshot.get("total_creators")
        task.created_at = snapshot.get("submitted_at") or task.created_at
        task.started_at = snapshot.get("started_at")
        task.finished_at = snapshot.get("finished_at")

        task.payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
        task.output_files = json.dumps(output_files, ensure_ascii=False) if output_files else None


def get_task_status(task_id: str) -> Optional[CrawlerTaskStatus]:
    with get_session() as db:
        task = db.get(OutreachTask, task_id)
        if not task:
            return None
        return _task_to_status(task)


def list_tasks(
    *,
    brand_name: Optional[str],
    region: Optional[str],
    status: Optional[str],
    task_name: Optional[str],
    run_at_time: Optional[datetime],
    run_end_time: Optional[datetime],
    page: int,
    page_size: int,
    sort: Optional[str],
) -> Tuple[List[CrawlerTaskStatus], int]:
    with get_session() as db:
        query = select(OutreachTask)

        if brand_name:
            query = query.where(
                func.lower(func.coalesce(OutreachTask.brand, "")).like(f"%{brand_name.lower()}%")
            )
        if region:
            query = query.where(func.lower(func.coalesce(OutreachTask.region, "")) == region.lower())
        if status:
            query = query.where(func.lower(func.coalesce(OutreachTask.status, "")) == status.lower())
        if task_name:
            name_like = f"%{task_name.lower()}%"
            query = query.where(
                func.lower(func.coalesce(OutreachTask.task_name, "")).like(name_like)
                | func.lower(OutreachTask.task_id).like(name_like)
            )

        # 默认按创建时间倒序
        order_column = OutreachTask.created_at.desc()
        if sort == "startAsc":
            order_column = OutreachTask.run_at_time.asc()
        elif sort == "startDesc":
            order_column = OutreachTask.run_at_time.desc()
        elif sort == "endAsc":
            order_column = OutreachTask.run_end_time.asc()
        elif sort == "endDesc":
            order_column = OutreachTask.run_end_time.desc()

        rows = db.execute(query.order_by(order_column)).scalars().all()

    def _match_time_filters(task: OutreachTask) -> bool:
        if run_at_time:
            candidate = _parse_datetime(task.run_at_time) or task.started_at or task.created_at
            if not candidate or candidate < run_at_time:
                return False
        if run_end_time:
            candidate_end = _parse_datetime(task.run_end_time) or task.finished_at
            if not candidate_end or candidate_end > run_end_time:
                return False
        return True

    filtered = [task for task in rows if _match_time_filters(task)]

    def _start_ts(task: OutreachTask) -> float:
        candidate = _parse_datetime(task.run_at_time) or task.started_at or task.created_at
        return candidate.timestamp() if isinstance(candidate, datetime) else float("-inf")

    def _end_ts(task: OutreachTask) -> float:
        candidate = _parse_datetime(task.run_end_time) or task.finished_at or task.created_at
        return candidate.timestamp() if isinstance(candidate, datetime) else float("inf")

    def _run_seconds(task: OutreachTask) -> int:
        started = task.started_at or _parse_datetime(task.run_at_time)
        finished = task.finished_at or _parse_datetime(task.run_end_time) or datetime.utcnow()
        if not started:
            return 0
        try:
            return max(0, int((finished - started).total_seconds()))
        except Exception:  # pragma: no cover
            return 0

    if sort == "startAsc":
        filtered.sort(key=_start_ts)
    elif sort == "startDesc":
        filtered.sort(key=_start_ts, reverse=True)
    elif sort == "endAsc":
        filtered.sort(key=_end_ts)
    elif sort == "endDesc":
        filtered.sort(key=_end_ts, reverse=True)
    elif sort == "timeAsc":
        filtered.sort(key=_run_seconds)
    elif sort == "timeDesc":
        filtered.sort(key=_run_seconds, reverse=True)
    else:
        filtered.sort(
            key=lambda task: task.created_at.timestamp() if isinstance(task.created_at, datetime) else float("-inf"),
            reverse=True,
        )
    total = len(filtered)

    safe_page = max(1, page)
    safe_page_size = max(1, min(200, page_size))
    start_index = (safe_page - 1) * safe_page_size
    end_index = start_index + safe_page_size
    paginated = filtered[start_index:end_index]
    statuses = [_task_to_status(task) for task in paginated]
    return statuses, total


def list_pending_task_snapshots(statuses: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """读取数据库中仍处于待执行状态的任务快照。"""
    ensure_outreach_task_schema()
    target_status = statuses or ["pending", "to-be-run"]
    lowered = [status.lower() for status in target_status]
    with get_session() as db:
        query = select(OutreachTask).where(
            func.lower(func.coalesce(OutreachTask.status, "")).in_(lowered)
        )
        rows = db.execute(query).scalars().all()
    return [_task_to_snapshot(task) for task in rows]


def cancel_incomplete_tasks_on_startup(statuses: Optional[List[str]] = None) -> int:
    """服务启动时，将所有未完成的任务标记为取消，避免界面长时间显示“进行中”"""
    ensure_outreach_task_schema()
    target_status = statuses or ["pending", "to-be-run", "running", "to-be-cancel"]
    lowered = [status.lower() for status in target_status]
    now_ts = now_beijing()
    with get_session() as db:
        rows = (
            db.query(OutreachTask)
            .filter(func.lower(func.coalesce(OutreachTask.status, "")).in_(lowered))
            .all()
        )
        if not rows:
            return 0
        for task in rows:
            task.status = "cancelled"
            auto_msg = "服务重启，任务自动取消"
            if task.message:
                if auto_msg not in task.message:
                    task.message = f"{task.message} | {auto_msg}"
            else:
                task.message = auto_msg
            task.finished_at = now_ts
        db.commit()
        return len(rows)
