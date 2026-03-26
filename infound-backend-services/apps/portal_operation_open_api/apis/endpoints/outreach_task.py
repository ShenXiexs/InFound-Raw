from fastapi import APIRouter, Query, Path, Depends

from apps.portal_operation_open_api.core.deps import get_outreach_task_service
from apps.portal_operation_open_api.services.outreach_task_service import (
    OutreachTaskService,
)
from core_base import success_response

router = APIRouter(
    prefix="/operation/tasks",
    tags=["operation-task"],
)

UUID_PATTERN = r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"


@router.get("")
async def list_outreach_tasks(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
        status: str | None = Query(None,
                                   description="任务状态: not_started, in_progress, cancelled, completed, failed"),
        region: str | None = Query(None, description="地区"),
        task_name: str | None = Query(None, description="任务名称"),
        platform: str | None = Query(None, description="平台"),
        service: OutreachTaskService = Depends(get_outreach_task_service),
):
    data = await service.get_task_list(
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
        service: OutreachTaskService = Depends(get_outreach_task_service),
):
    data = await service.get_task_detail(
        task_id=task_id,
    )
    return success_response(data)
