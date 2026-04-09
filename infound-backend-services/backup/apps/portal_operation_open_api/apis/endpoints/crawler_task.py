from fastapi import APIRouter, Query, Path

from common.core.database import DatabaseManager
from common.core.response import success_response
from common.services.rabbitmq_producer import RabbitMQProducer
from apps.portal_operation_open_api.services.outreach_task_service import (
    OutreachTaskService,
)
from apps.portal_operation_open_api.models.create_task import (
    CreateTaskRequest,
    UpdateTaskRequest,
    UpdateTaskNameRequest,
)


router = APIRouter(
    prefix="/operation/tasks",
    tags=["operation-task"],
)

UUID_PATTERN = r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"


@router.get("")
async def list_crawler_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: str | None = Query(None, description="任务状态: not_started, in_progress, cancelled, completed, failed"),
    sort_by: str | None = Query(None, description="排序字段"),
    sort_order: str | None = Query(None, description="排序方向: asc/desc"),
    created_from: str | None = Query(None, description="创建开始时间"),
    created_to: str | None = Query(None, description="创建结束时间"),
    plan_start_from: str | None = Query(None, description="计划开始时间(起)"),
    plan_start_to: str | None = Query(None, description="计划开始时间(止)"),
    plan_end_from: str | None = Query(None, description="计划结束时间(起)"),
    plan_end_to: str | None = Query(None, description="计划结束时间(止)"),
    region: str | None = Query(None, description="地区"),
    task_name: str | None = Query(None, description="任务名称"),
    platform: str | None = Query(None, description="平台"),
):
    """
    查询爬虫任务列表
    """
    async with DatabaseManager.get_session() as session:
        data = await OutreachTaskService.get_task_list(
            session=session,
            page=page,
            page_size=page_size,
            status=status,
            region=region,
            task_name=task_name,
            platform=platform,
            sort_by=sort_by,
            sort_order=sort_order,
            created_from=created_from,
            created_to=created_to,
            plan_start_from=plan_start_from,
            plan_start_to=plan_start_to,
            plan_end_from=plan_end_from,
            plan_end_to=plan_end_to,
        )
        return success_response(data)


@router.get("/{task_id}")
async def get_crawler_task(
    task_id: str = Path(..., description="任务ID", pattern=UUID_PATTERN),
):
    """
    查询单个任务
    """
    async with DatabaseManager.get_session() as session:
        data = await OutreachTaskService.get_task_detail(
            session=session,
            task_id=task_id,
        )
        return success_response(data)


@router.post("")
async def create_crawler_task(payload: CreateTaskRequest):
    """
    新建活动任务
    """
    async with DatabaseManager.get_session() as session:
        task = await OutreachTaskService.create_task(session, payload)
        crawler_payload = OutreachTaskService.build_crawler_payload(task)
        await RabbitMQProducer.publish_crawler_task(crawler_payload)
        return success_response({"task_id": task.id})


@router.put("/{task_id}")
async def update_crawler_task(
    task_id: str = Path(..., description="任务ID", pattern=UUID_PATTERN),
    payload: UpdateTaskRequest = ...,
):
    """
    编辑保存活动任务
    """
    async with DatabaseManager.get_session() as session:
        task = await OutreachTaskService.update_task(session, task_id, payload)
        return success_response({"task_id": task.id})


@router.get("/{task_id}/run-now")
async def run_task_now(
    task_id: str = Path(..., description="任务ID", pattern=UUID_PATTERN),
):
    """
    立即执行任务
    """
    async with DatabaseManager.get_session() as session:
        try:
            task = await OutreachTaskService.run_task_now(session, task_id)
            crawler_payload = OutreachTaskService.build_crawler_payload(task)
            await RabbitMQProducer.publish_crawler_task(crawler_payload)
            return success_response({
                "task_id": task.id,
                "message": "任务已设为立即执行",
            })
        except ValueError as exc:
            return success_response({"error": str(exc)}, code=400)


@router.patch("/{task_id}/task-name")
async def update_task_name(
    task_id: str = Path(..., description="任务ID", pattern=UUID_PATTERN),
    payload: UpdateTaskNameRequest = ...,
):
    """
    修改任务名称
    """
    async with DatabaseManager.get_session() as session:
        task = await OutreachTaskService.update_task_name(
            session=session,
            task_id=task_id,
            task_name=payload.task_name,
        )
        return success_response({"task_id": task.id, "task_name": task.task_name})
