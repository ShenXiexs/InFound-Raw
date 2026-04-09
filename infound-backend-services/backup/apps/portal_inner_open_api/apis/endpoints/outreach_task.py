from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.database import get_db_session
from common.core.response import APIResponse, success_response
from apps.portal_inner_open_api.models.outreach_task import (
    OutreachTaskIngestionRequest,
    OutreachTaskIngestionResult,
    OutreachTaskProgressRequest,
    OutreachTaskProgressResult,
)
from apps.portal_inner_open_api.services.outreach_task_service import (
    outreach_task_service,
)

router = APIRouter(prefix="/outreach_tasks", tags=["OutreachTasks"])


@router.post(
    "/ingest",
    response_model=APIResponse[OutreachTaskIngestionResult],
    response_model_by_alias=True,
)
async def ingest_outreach_task(
    payload: OutreachTaskIngestionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[OutreachTaskIngestionResult]:
    try:
        result = await outreach_task_service.ingest(payload, session)
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
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[OutreachTaskProgressResult]:
    try:
        new_count = await outreach_task_service.increment_progress(
            task_id=payload.task_id,
            delta=payload.delta,
            operator_id=payload.operator_id,
            session=session,
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
