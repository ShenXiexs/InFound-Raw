from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import json

# 1. Shared dependencies
from common.core.database import get_db_session
from common.core.response import APIResponse, success_response
# NOTE: Products is required for join queries
from common.models.infound import Samples, Products

# 2. DTOs and entities
# SampleDetailResponse is dedicated to this endpoint
from apps.portal_creator_open_api.models.dtos.sample import SampleDetailResponse
from apps.portal_creator_open_api.models.dtos.ad_code import SubmitAdCodeRequest
from apps.portal_creator_open_api.models.entities import CurrentUserInfo

# Router with tag
router = APIRouter(tags=["Samples"])

@router.get(
    "/sample/detail/{sampleId}",
    response_model=APIResponse[SampleDetailResponse],
    response_model_by_alias=True,
)
async def get_sample_detail(
        sampleId: str,
        request: Request,
        db: Annotated[AsyncSession, Depends(get_db_session)]
) -> APIResponse[SampleDetailResponse]:
    """
    Fetch sample details by ID.
    """

    # 1. Verify token (from request.state)
    if not hasattr(request.state, "current_user_info"):
        raise HTTPException(status_code=401, detail="Unverified")

    user: CurrentUserInfo = request.state.current_user_info

    # 2. Query: join Samples and Products
    stmt = (
        select(Samples, Products)
        .join(Products, Samples.platform_product_id == Products.platform_product_id)
        .where(
            and_(
                # Must match ID in URL
                Samples.id == sampleId,
                # Must match current user (authz)
                Samples.platform_creator_username == user.platform_creator_username
            )
        )
    )

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Sample not found or access denied")

    sample_record: Samples = row[0]
    product_record: Products = row[1]

    # 3. Build response
    response_data = SampleDetailResponse(
        id=sample_record.id,
        status=sample_record.status,
        content_summary=sample_record.content_summary,
        ad_code=sample_record.ad_code,

        platform_product_id=product_record.platform_product_id,
        product_name=product_record.product_name,
        thumbnail=product_record.thumbnail,
        shooting_guide=product_record.shooting_guide,

        platform_creator_username=user.platform_creator_username,
        platform_creator_display_name=user.platform_creator_display_name,
        email=user.email,
        whatsapp=user.whatsapp
    )

    return success_response(data=response_data)

@router.post(
    "/creator/samples/{sample_id}/ad-codes",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def submit_ad_code(
        sample_id: str,
        req: SubmitAdCodeRequest,
        request: Request,
        db: Annotated[AsyncSession, Depends(get_db_session)]
) -> APIResponse[dict]:
    """Creator submits AD code."""

    if not hasattr(request.state, "current_user_info"):
        raise HTTPException(status_code=401, detail="Unverified")

    current: CurrentUserInfo = request.state.current_user_info

    # 1. Verify sample ownership
    stmt = select(Samples).where(
        Samples.id == sample_id,
        Samples.platform_creator_username == current.platform_creator_username
    )
    sample = (await db.execute(stmt)).scalar_one_or_none()

    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found or unauthorized")

    # 2. Ensure ad_codes is a JSON array
    try:
        parsed = json.loads(req.ad_codes)
        if not isinstance(parsed, list):
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=400, detail="ad_codes must be a JSON array string")

    # 3. Persist update
    sample.ad_code = req.ad_codes
    await db.commit()

    return success_response({"message": "AD Code submitted successfully"})
