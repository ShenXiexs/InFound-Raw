"""
爬虫任务API
"""
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from zoneinfo import ZoneInfo

from api.deps import get_current_active_user
from schemas.card import CardTaskStatus
from schemas.crawler import (
    CrawlerSummaryResponse,
    CrawlerTaskCreateRequest,
    CrawlerTaskListResponse,
    CrawlerTaskStatus,
    CrawlerTaskUpdateRequest,
    CrawlerTaskRenameRequest,
)
from services.crawler_service import get_crawler_service
from services.card_service import get_card_service
from utils.response import create_response

router = APIRouter()

_ALLOWED_TASK_TYPES = {"Connect", "Card"}


def _normalize_task_type(task_type: Optional[str]) -> Optional[str]:
    if task_type is None:
        return None
    normalized = task_type.strip().lower()
    return {"connect": "Connect", "card": "Card"}.get(normalized)


def _format_run_time(started_at: Optional[datetime], finished_at: Optional[datetime]) -> Optional[str]:
    if not started_at:
        return None
    end_time = finished_at
    if end_time is None:
        try:
            end_time = datetime.now(tz=started_at.tzinfo) if started_at.tzinfo else datetime.utcnow()
        except Exception:  # pragma: no cover
            end_time = datetime.utcnow()
    try:
        delta = end_time - started_at
    except TypeError:
        delta = end_time.replace(tzinfo=None) - started_at.replace(tzinfo=None)

    total_seconds = max(int(delta.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h{minutes:02d}min{seconds:02d}s"


def _card_task_to_crawler_status(card_task: CardTaskStatus) -> CrawlerTaskStatus:
    output_files = list(card_task.output_files) if card_task.output_files else []
    if not output_files and card_task.output_json:
        output_files.append(card_task.output_json)

    payload: Dict[str, Any] = {
        "creator_file": card_task.creator_file,
        "product_file": card_task.product_file,
        "record_count": card_task.record_count,
        "generate_only": card_task.generate_only,
    }

    return CrawlerTaskStatus(
        task_id=card_task.task_id,
        task_type="Card",
        status=card_task.status,
        message=card_task.message,
        submitted_at=card_task.created_at,
        started_at=card_task.started_at,
        finished_at=card_task.finished_at,
        user=card_task.created_by,
        task_name=None,
        campaign_id=None,
        campaign_name=None,
        region=None,
        brand_name=None,
        account_email=None,
        new_creators=None,
        total_creators=card_task.record_count,
        task_dir=card_task.task_dir,
        log_path=None,
        product_name=None,
        product_id=None,
        connect_creator=None,
        run_time=_format_run_time(card_task.started_at, card_task.finished_at),
        payload=payload,
        output_files=output_files,
        max_creators=None,
        target_new_creators=card_task.record_count,
        run_at_time=card_task.created_at,
        run_end_time=card_task.finished_at,
    )


def _filter_card_tasks(
    card_tasks: List[CardTaskStatus],
    *,
    task_name: Optional[str] = None,
    status: Optional[str] = None,
) -> List[CardTaskStatus]:
    filtered = card_tasks
    if status:
        status_lower = status.strip().lower()
        filtered = [t for t in filtered if t.status.lower() == status_lower]

    if task_name:
        keyword = task_name.strip().lower()
        filtered = [
            t
            for t in filtered
            if keyword in t.task_id.lower()
            or (t.task_dir and keyword in t.task_dir.lower())
            or (t.output_json and keyword in t.output_json.lower())
        ]

    return filtered


def _fetch_tasks(
    *,
    task_type: Optional[str],
    service,
    brand_name: Optional[str],
    region: Optional[str],
    status: Optional[str],
    task_name: Optional[str],
    run_at_time: Optional[datetime],
    run_end_time: Optional[datetime],
    page: int,
    page_size: int,
    sort: Optional[str],
) -> CrawlerTaskListResponse:
    normalized_type = task_type or "Connect"
    if normalized_type == "Card":
        card_service = get_card_service()
        card_tasks = card_service.list_tasks()
        filtered = _filter_card_tasks(card_tasks, task_name=task_name, status=status)
        total = len(filtered)
        start = max(page - 1, 0) * page_size
        end = start + page_size
        paginated = filtered[start:end]
        statuses = [_card_task_to_crawler_status(task) for task in paginated]
        return CrawlerTaskListResponse(tasks=statuses, total=total)

    tasks, total = service.list_tasks(
        brand_name=brand_name,
        region=region,
        status=status,
        task_name=task_name,
        run_at_time=run_at_time,
        run_end_time=run_end_time,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return CrawlerTaskListResponse(tasks=tasks, total=total)


@router.post("/tasks", summary="创建并启动爬虫任务")
async def create_task(
    task_data: CrawlerTaskCreateRequest,
    current_user: dict = Depends(get_current_active_user),
):
    """
    创建新的爬虫任务并立即后台执行。
    返回任务ID，后续可通过任务ID查询状态或结果。
    """
    service = get_crawler_service()
    task_id = service.submit_task(task_data, created_by=current_user["username"])
    return create_response(
        success=True,
        message="任务已创建并进入队列",
        data={"task_id": task_id},
    )


def _parse_query_datetime(value: Optional[str]) -> Optional[datetime]:
    if value in (None, ""):
        return None
    candidate = value.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(candidate, fmt)
            return dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return dt
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"无法解析时间 {value}") from exc


@router.get("/tasks", summary="获取任务列表", response_model=CrawlerTaskListResponse)
async def list_tasks(
    brand_name: Optional[str] = Query(None, description="按品牌名模糊匹配"),
    region: Optional[str] = Query(None, description="区域代码"),
    status: Optional[str] = Query(None, description="任务状态"),
    run_at_time: Optional[str] = Query(
        None, description="开始时间下限（YYYY-MM-DD 或 YYYY-MM-DD HH:MM）"
    ),
    run_end_time: Optional[str] = Query(
        None, description="结束时间上限（YYYY-MM-DD 或 YYYY-MM-DD HH:MM）"
    ),
    task_name: Optional[str] = Query(None, description="按任务名称模糊匹配"),
    task_type: Optional[str] = Query(
        None, description="任务类型：Connect 或 Card"
    ),
    page_num: int = Query(1, ge=1, alias="pageNum", description="页码，默认1"),
    page_size: int = Query(20, ge=1, alias="pageSize", description="每页数量，默认20"),
    sort: Optional[str] = Query(
        None,
        description="排序方式：startAsc/startDesc/endAsc/endDesc/timeAsc/timeDesc",
    ),
    current_user: dict = Depends(get_current_active_user),
):
    """获取近期任务列表（按提交时间倒序）。"""
    service = get_crawler_service()
    allowed_sorts = {"startAsc", "startDesc", "endAsc", "endDesc", "timeAsc", "timeDesc"}
    sort_value = sort.strip() if sort else None
    if sort_value and sort_value not in allowed_sorts:
        raise HTTPException(status_code=400, detail="非法的排序方式")

    normalized_task_type = _normalize_task_type(task_type) if task_type else None
    if task_type and not normalized_task_type:
        raise HTTPException(status_code=400, detail="任务类型只能为 Connect 或 Card")

    start_dt = _parse_query_datetime(run_at_time) if run_at_time else None
    end_dt = _parse_query_datetime(run_end_time) if run_end_time else None
    safe_page_size = min(page_size, 200)

    response = _fetch_tasks(
        task_type=normalized_task_type,
        service=service,
        brand_name=brand_name,
        region=region,
        status=status,
        task_name=task_name,
        run_at_time=start_dt,
        run_end_time=end_dt,
        page=page_num,
        page_size=safe_page_size,
        sort=sort_value,
    )
    return response


@router.get(
    "/tasks/search",
    summary="按任务名称搜索任务",
    response_model=CrawlerTaskListResponse,
)
async def search_tasks(
    task_name: str = Query(..., description="任务名称关键词"),
    task_type: str = Query("Connect", description="任务类型：Connect 或 Card"),
    status: Optional[str] = Query(None, description="按任务状态过滤"),
    page_num: int = Query(1, ge=1, alias="pageNum", description="页码，默认1"),
    page_size: int = Query(20, ge=1, alias="pageSize", description="每页数量，默认20"),
    current_user: dict = Depends(get_current_active_user),
):
    service = get_crawler_service()
    normalized_task_type = _normalize_task_type(task_type)
    if not normalized_task_type:
        raise HTTPException(status_code=400, detail="任务类型只能为 Connect 或 Card")

    safe_page_size = min(page_size, 200)
    response = _fetch_tasks(
        task_type=normalized_task_type,
        service=service,
        brand_name=None,
        region=None,
        status=status,
        task_name=task_name,
        run_at_time=None,
        run_end_time=None,
        page=page_num,
        page_size=safe_page_size,
        sort=None,
    )
    return response


@router.get(
    "/tasks/by-type",
    summary="按任务类型筛选任务",
    response_model=CrawlerTaskListResponse,
)
async def list_tasks_by_type(
    task_type: str = Query(..., description="任务类型：Connect 或 Card"),
    status: Optional[str] = Query(None, description="按任务状态过滤"),
    page_num: int = Query(1, ge=1, alias="pageNum", description="页码，默认1"),
    page_size: int = Query(20, ge=1, alias="pageSize", description="每页数量，默认20"),
    current_user: dict = Depends(get_current_active_user),
):
    service = get_crawler_service()
    normalized_task_type = _normalize_task_type(task_type)
    if not normalized_task_type:
        raise HTTPException(status_code=400, detail="任务类型只能为 Connect 或 Card")

    safe_page_size = min(page_size, 200)
    response = _fetch_tasks(
        task_type=normalized_task_type,
        service=service,
        brand_name=None,
        region=None,
        status=status,
        task_name=None,
        run_at_time=None,
        run_end_time=None,
        page=page_num,
        page_size=safe_page_size,
        sort=None,
    )
    return response


@router.get(
    "/tasks/{task_id}",
    summary="获取任务详情",
    response_model=CrawlerTaskStatus,
)
async def get_task(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    """通过任务ID获取任务详情。"""
    service = get_crawler_service()
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.delete("/tasks/{task_id}", summary="取消任务")
async def cancel_task(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    """
    取消仍在排队或未开始的任务。
    对于已经运行的 Playwright 任务无法强制中断，只会返回失败。
    """
    service = get_crawler_service()
    cancelled = service.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(status_code=409, detail="任务无法取消或已完成")
    return create_response(success=True, message="任务已取消")


@router.post("/tasks/{task_id}/force-stop", summary="强制终止任务")
async def force_stop_task(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    """
    无论任务是否已经开始执行，都尝试立即发出终止指令。
    实际执行线程会尽快响应终止。
    """
    service = get_crawler_service()
    forced = service.force_cancel_task(task_id)
    if not forced:
        raise HTTPException(status_code=404, detail="任务不存在")
    return create_response(success=True, message="强制终止指令已发送")


@router.post("/tasks/{task_id}/run-now", summary="立即执行任务")
async def run_task_now(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    service = get_crawler_service()
    try:
        service.run_task_now(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return create_response(success=True, message="任务已设为立即执行")


@router.put(
    "/tasks/{task_id}",
    summary="更新待执行任务",
    response_model=CrawlerTaskStatus,
)
async def update_task(
    task_id: str,
    update_data: CrawlerTaskUpdateRequest,
    current_user: dict = Depends(get_current_active_user),
):
    service = get_crawler_service()
    try:
        service.update_task(task_id, update_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    updated = service.get_task(task_id)
    if not updated:
        raise HTTPException(status_code=404, detail="任务不存在")
    return updated


@router.patch(
    "/tasks/{task_id}/task-name",
    summary="仅修改任务名称",
    response_model=CrawlerTaskStatus,
)
async def rename_task(
    task_id: str,
    rename_data: CrawlerTaskRenameRequest,
    current_user: dict = Depends(get_current_active_user),
):
    service = get_crawler_service()
    try:
        service.rename_task(task_id, rename_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    updated = service.get_task(task_id)
    if not updated:
        raise HTTPException(status_code=404, detail="任务不存在")
    return updated


@router.get("/summary", summary="获取任务汇总", response_model=CrawlerSummaryResponse)
async def get_summary(
    current_user: dict = Depends(get_current_active_user),
):
    """获取当前任务运行的整体统计信息。"""
    service = get_crawler_service()
    return service.get_summary()


@router.get("/tasks/{task_id}/log", summary="获取任务日志")
async def get_task_log(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    """
    返回指定任务的日志内容。
    若日志尚未生成或任务不存在将返回404。
    """
    service = get_crawler_service()
    task = service.get_task(task_id)
    if not task or not task.log_path:
        raise HTTPException(status_code=404, detail="日志不存在或任务未找到")

    log_path = Path(task.log_path)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="日志文件不存在")

    return create_response(
        success=True,
        data={
            "task_id": task_id,
            "log_path": str(log_path),
            "content": log_path.read_text(encoding="utf-8", errors="ignore")[-20000:],
        },
    )
