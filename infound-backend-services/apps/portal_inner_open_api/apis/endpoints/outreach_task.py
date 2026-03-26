from fastapi import APIRouter, Depends, HTTPException, status

from apps.portal_inner_open_api.core.deps import (
    get_outreach_task_service,
)
from apps.portal_inner_open_api.models.outreach_task import (
    OutreachTaskIngestionRequest,
    OutreachTaskIngestionResult,
    OutreachTaskProgressRequest,
    OutreachTaskProgressResult,
)
from apps.portal_inner_open_api.services.outreach_task_service import (
    OutreachTaskService,
)
from core_base import APIResponse, success_response

router = APIRouter(prefix="/outreach_tasks", tags=["OutreachTasks"])


@router.post(
    "/ingest",
    response_model=APIResponse[OutreachTaskIngestionResult],
    response_model_by_alias=True,
)
async def ingest_outreach_task(
    payload: OutreachTaskIngestionRequest,
    service: OutreachTaskService = Depends(get_outreach_task_service),
) -> APIResponse[OutreachTaskIngestionResult]:
    try:
        result = await service.ingest(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


@router.post(
    "/progress",
    response_model=APIResponse[OutreachTaskProgressResult],
    response_model_by_alias=True,
)
async def increment_outreach_progress(
    payload: OutreachTaskProgressRequest,
    service: OutreachTaskService = Depends(get_outreach_task_service),
) -> APIResponse[OutreachTaskProgressResult]:
    try:
        new_count = await service.increment_progress(
            task_id=payload.task_id,
            delta=payload.delta,
            operator_id=payload.operator_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    result = OutreachTaskProgressResult(
        task_id=payload.task_id,
        new_creators_real_count=new_count,
    )
    return success_response(result)
