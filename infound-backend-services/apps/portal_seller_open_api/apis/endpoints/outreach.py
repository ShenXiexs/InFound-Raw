from fastapi import APIRouter, Depends, HTTPException, Request, status

from apps.portal_seller_open_api.core.deps import get_outreach_result_service
from apps.portal_seller_open_api.models.outreach_result import (
    OutreachResultIngestionRequest,
    OutreachResultIngestionResult,
)
from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from apps.portal_seller_open_api.services.outreach_result_service import (
    OutreachResultIngestionService,
)
from core_base import APIResponse, success_response

router = APIRouter(prefix="/api/v1/rpa/outreach", tags=["Seller RPA Outreach"])


@router.post(
    "/results",
    response_model=APIResponse[OutreachResultIngestionResult],
    response_model_by_alias=True,
)
async def ingest_outreach_results(
    payload: OutreachResultIngestionRequest,
    request: Request,
    service: OutreachResultIngestionService = Depends(get_outreach_result_service),
) -> APIResponse[OutreachResultIngestionResult]:
    current_user: CurrentUserInfo = request.state.current_user_info
    try:
        result = await service.ingest(current_user, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
