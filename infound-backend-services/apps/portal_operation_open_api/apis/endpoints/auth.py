import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, and_
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_operation_open_api.core.config import Settings
from apps.portal_operation_open_api.core.deps import get_db_session, get_token_manager, get_settings
from apps.portal_operation_open_api.core.token_manager import TokenManager
from apps.portal_operation_open_api.models.auth import LoginRequest
from apps.portal_operation_open_api.models.entities import CurrentUserInfo
from core_base import get_logger, APIResponse, success_response
from shared_domain.models.infound import OpsUsers

router = APIRouter(
    prefix="/auth",
    tags=["用户"],
)
logger = get_logger()


@router.post(
    "/login",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def login_for_access_token(
        request: LoginRequest,
        db: Annotated[AsyncSession, Depends(get_db_session)],
        settings: Settings = Depends(get_settings),
        token_manager: TokenManager = Depends(get_token_manager),
) -> APIResponse[dict]:
    """获取 JWT 令牌（登录）"""
    try:
        # 1. 根据用户名查询用户
        sql = select(OpsUsers).where(
            and_(
                OpsUsers.user_name == request.username,
                (OpsUsers.deleted.is_(None)) | (OpsUsers.deleted == 0)
            )
        )
        user: OpsUsers = (await db.execute(sql)).scalar_one_or_none()

        if not user:
            logger.info(f"SQL: {sql.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True})}")
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )

        # 2. 验证账号状态
        if user.status is not None and user.status != 0:
            raise HTTPException(
                status_code=403,
                detail="Account is disabled"
            )

        # 3. 验证密码
        if not token_manager.verify_password(request.password, user.password):
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )

        # 4. 创建访问令牌
        jti = str(int(time.time()))

        # 5. 构建用户信息并保存到 Redis
        current_user_info = CurrentUserInfo(
            jti=jti,
            user_id=user.id,
            user_name=user.user_name,
            nick_name=user.nick_name,
            user_type=user.user_type,
            email=user.email,
            phone_number=user.phone_number,
            sex=user.sex,
            avatar=user.avatar,
            status=user.status,
            dept_id=user.dept_id,
        )

        access_token = token_manager.create_access_token(current_user_info)

        return success_response(data={
            "jti": jti,
            "header": settings.auth.required_header,
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
    "/me",
    response_model=APIResponse[CurrentUserInfo],
    response_model_by_alias=True,
)
async def get_current_user(request: Request) -> APIResponse[CurrentUserInfo]:
    """获取当前用户信息"""
    if not hasattr(request.state, "current_user_info"):
        raise HTTPException(status_code=401, detail="Unverified")

    current_user_info = request.state.current_user_info
    return success_response(data=current_user_info)
