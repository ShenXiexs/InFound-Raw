import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_creator_open_api.models.dtos.account import LoginRequest
from apps.portal_creator_open_api.models.entities import CurrentUserInfo
from apps.portal_creator_open_api.services.security import create_access_token, save_token_to_redis
from common import app_constants
from common.core.database import get_db_session
from common.core.logger import get_logger
from common.core.response import APIResponse, success_response
from common.models.infound import Samples, Creators

router = APIRouter(tags=["账号"])
logger = get_logger()


@router.post(
    "/account/login",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def login_for_access_token(
        request: LoginRequest,
        db: Annotated[AsyncSession, Depends(get_db_session)]
) -> APIResponse[dict]:
    """获取 JWT 令牌（登录）"""
    try:
        sample: Samples = (await db.execute(
            select(Samples)
            .where(
                and_(
                    Samples.id == request.sample_id,
                    Samples.platform_creator_username == request.user_name
                )
            )
        )).scalar_one_or_none()

        if not sample:
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )

        # 创建访问令牌
        jti = str(int(time.time()))
        access_token = create_access_token(
            {
                "sub": sample.platform_creator_username,
                "creator_id": sample.id,
                "jti": jti
            }
        )

        if access_token:
            creator: Creators = (await db.execute(
                select(Creators)
                .where(Creators.platform_creator_username == request.user_name)
            )).scalar_one_or_none()

            if creator is not None:
                current_user_info = CurrentUserInfo(
                    jti=jti,
                    if_id=creator.id,
                    platform_creator_id=creator.platform_creator_id,
                    platform_creator_username=creator.platform_creator_username,
                    platform_creator_display_name=creator.platform_creator_display_name,
                    email=creator.email,
                    whatsapp=creator.whatsapp,
                )
                save_token_to_redis(current_user_info, access_token)
            else:
                # TODO: 理论上如果 creator 表不存在数据，那这个登录是有问题的，现在先这样处理，后面流程跑顺了，再看看怎么解决。
                current_user_info = CurrentUserInfo(
                    jti=jti,
                    if_id='',
                    platform_creator_id='',
                    platform_creator_username=request.user_name,
                    platform_creator_display_name=request.user_name,
                    email='',
                    whatsapp='',
                )
                save_token_to_redis(current_user_info, access_token)

        return success_response(data={
            "jti": jti,
            "header": app_constants.CREATOR_ACCESS_TOKEN_HEADER,
            "token": access_token,
        })

    # 捕获 HTTPException 直接往上抛，不要被下面的 Exception 拦截成 500
    except HTTPException as http_ex:
        raise http_ex

    # 捕获所有其他未知异常
    except Exception as e:
        # 记录错误日志
        logger.error(f"Login failed unexpectedly: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"  # 给前端统一的错误提示，不暴露内部异常
        )


@router.get(
    "/account/me",
    response_model=APIResponse[CurrentUserInfo],
    response_model_by_alias=True,
)
async def get_current_user(request: Request) -> APIResponse[CurrentUserInfo]:
    """获取当前用户信息"""
    if not hasattr(request.state, "current_user_info"):
        raise HTTPException(status_code=401, detail="Unverified")

    current_user_info = request.state.current_user_info
    return success_response(data=current_user_info)
