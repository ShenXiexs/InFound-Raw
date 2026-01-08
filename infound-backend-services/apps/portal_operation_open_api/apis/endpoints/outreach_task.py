from fastapi import APIRouter, Query, Path

from common.core.database import DatabaseManager
from common.core.response import success_response
from apps.portal_operation_open_api.services.outreach_task_service import (
    OutreachTaskService,
)
from apps.portal_operation_open_api.models.create_task import CreateTaskRequest, UpdateTaskRequest



router = APIRouter(
    prefix="/operation/tasks",
    tags=["operation-task"],
)

UUID_PATTERN = r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"


@router.get("")
async def list_outreach_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: str | None = Query(None, description="任务状态: not_started, in_progress, cancelled, completed, failed"),
    region: str | None = Query(None, description="地区"),
    task_name: str | None = Query(None, description="任务名称"),
    platform: str | None = Query(None, description="平台"),
):
    async with DatabaseManager.get_session() as session:
        data = await OutreachTaskService.get_task_list(
            session=session,
            page=page,
            page_size=page_size,
            status=status,
            region=region,
            task_name=task_name,
            platform=platform,
        )
        return success_response(data)


@router.get("/{task_id}")
async def get_outreach_task(
    task_id: str = Path(..., description="任务ID", pattern=UUID_PATTERN),
):
    async with DatabaseManager.get_session() as session:
        data = await OutreachTaskService.get_task_detail(
            session=session,
            task_id=task_id,
        )
        return success_response(data)
