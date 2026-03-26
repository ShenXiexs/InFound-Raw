from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_creator_open_api.core.deps import get_db_session

# 2. 导入 DTO 和 实体
# SampleDetailResponse 专门用于这个接口
from apps.portal_creator_open_api.models.dtos.sample import SampleDetailResponse
from apps.portal_creator_open_api.models.entities import CurrentUserInfo
from shared_domain.models.infound import Samples, Products
from core_base import APIResponse, success_response

# 定义路由，标签设为 "样品"
router = APIRouter(tags=["样品"])


@router.get(
    "/sample/detail/{sampleId}",
    response_model=APIResponse[SampleDetailResponse],
    response_model_by_alias=True,
)
async def get_sample_detail(
    sampleId: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> APIResponse[SampleDetailResponse]:
    """
    查询指定样品的详情 (独立出来的接口)
    """

    # 1. 验证 Token (从 request.state 获取)
    if not hasattr(request.state, "current_user_info"):
        raise HTTPException(status_code=401, detail="Unverified")

    user: CurrentUserInfo = request.state.current_user_info

    # 2. 数据库查询：关联 Samples 和 Products
    stmt = (
        select(Samples, Products)
        .join(Products, Samples.platform_product_id == Products.platform_product_id)
        .where(
            and_(
                # 必须匹配 URL 里的 ID
                Samples.id == sampleId,
                # 必须匹配当前登录用户的用户名 (权限控制)
                Samples.platform_creator_username == user.platform_creator_username,
            )
        )
    )

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Sample not found or access denied")

    sample_record: Samples = row[0]
    product_record: Products = row[1]

    # 3. 组装返回数据
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
        whatsapp=user.whatsapp,
    )

    return success_response(data=response_data)
