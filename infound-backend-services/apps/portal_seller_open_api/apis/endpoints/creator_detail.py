from fastapi import APIRouter, Depends, HTTPException, Request, status

from apps.portal_seller_open_api.core.deps import get_creator_detail_result_service
from apps.portal_seller_open_api.models.creator_detail_result import (
    CreatorDetailResultIngestionRequest,
    CreatorDetailResultIngestionResult,
)
from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from apps.portal_seller_open_api.services.creator_detail_result_service import (
    CreatorDetailResultIngestionService,
)
from core_base import APIResponse, success_response

router = APIRouter(
    prefix="/api/v1/rpa/creator-details",
    tags=["Seller RPA Creator Detail"],
)


@router.post(
    "/results",
    response_model=APIResponse[CreatorDetailResultIngestionResult],
    response_model_by_alias=True,
)
async def ingest_creator_detail_results(
    payload: CreatorDetailResultIngestionRequest,
    request: Request,
    service: CreatorDetailResultIngestionService = Depends(
        get_creator_detail_result_service
    ),
) -> APIResponse[CreatorDetailResultIngestionResult]:
    current_user: CurrentUserInfo = request.state.current_user_info
    try:
        result = await service.ingest(current_user, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
