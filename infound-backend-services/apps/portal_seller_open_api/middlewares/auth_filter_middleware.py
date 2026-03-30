import re

from fastapi import Request, FastAPI
from sqlalchemy import and_, select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from apps.portal_seller_open_api.app_constants import HEADER_DEVICE_ID
from apps.portal_seller_open_api.core.deps import get_settings, get_token_manager
from apps.portal_seller_open_api.exceptions import ErrorCodes
from core_base import get_logger, error_response
from shared_domain import DatabaseManager
from shared_domain.models.infound import IfIdentityUsers


class AuthFilterMiddleware(BaseHTTPMiddleware):
    """
    身份验证中间件：
    1. 检查 Header 中的 AccessToken
    2. 验证 Token 有效性及 Redis 存在性
    3. 将用户信息存入 request.state，供后续请求使用
    """

    def __init__(self, app: FastAPI):
        super().__init__(app)
        self.logger = get_logger()

    EXCLUDE_PATH_PATTERNS = [
        r"^/account/.*$",
        r"^/$",
        r"^/health$",
        r"^/docs.*",
        r"^/redoc.*",
        r"^/openapi.json$",
    ]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        if any(re.match(pattern, request.url.path) for pattern in self.EXCLUDE_PATH_PATTERNS):
            return await call_next(request)

        settings = get_settings(request)
        token_manager = get_token_manager(request)

        # 1. 获取 Header 中的 AccessToken
        token = request.headers.get(settings.auth.required_header)
        if not token:
            return JSONResponse(
                status_code=401,
                content=error_response(message="Token 无效", code=ErrorCodes.INVALID_TOKEN, data=None).model_dump(),
            )

        # 2. 验证 Token 并解析用户信息
        payload = token_manager.decode_access_token(token)
        if not payload:
            return JSONResponse(
                status_code=401,
                content=error_response(message="Token 无效", code=ErrorCodes.INVALID_TOKEN).model_dump(),
            )
        username: str = payload.get("sub")
        token_jti: str = payload.get("jti")
        if not username or not token_jti:
            return JSONResponse(
                status_code=401,
                content=error_response(message="Token 无效", code=ErrorCodes.INVALID_TOKEN).model_dump()
            )

        # 3. 检查 Token 是否在 Redis 中（未被登出）
        redis_valid = token_manager.is_token_valid_in_redis(username, token_jti)
        if not redis_valid:
            return JSONResponse(
                status_code=401,
                content=error_response(message="Token 无效", code=ErrorCodes.INVALID_TOKEN).model_dump(),
            )

        # 4. 构建用户对象并存入 request.state
        xunda_device_id = request.headers.get(HEADER_DEVICE_ID)
        try:
            current_user_info = token_manager.get_current_user_info(username, token_jti)
        except Exception as e:
            self.logger.error(f"读取当前会话失败: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=401,
                content=error_response(message="Token 已失效", code=ErrorCodes.INVALID_TOKEN).model_dump(),
            )

        if not current_user_info or not current_user_info.device_id or not current_user_info.user_id:
            return JSONResponse(
                status_code=401,
                content=error_response(message="Token 已失效", code=ErrorCodes.INVALID_TOKEN).model_dump()
            )
        if current_user_info.device_id != xunda_device_id:
            return JSONResponse(
                status_code=401,
                content=error_response(message="Token 已失效", code=ErrorCodes.INVALID_TOKEN).model_dump()
            )

        # 5. 业务用户存在性校验
        try:
            async with DatabaseManager.get_session() as session:
                user_stmt = select(IfIdentityUsers).where(
                    and_(
                        IfIdentityUsers.id == current_user_info.user_id,
                        (IfIdentityUsers.deleted.is_(None)) | (IfIdentityUsers.deleted == 0),
                    )
                )
                result = await session.execute(user_stmt)
                try:
                    identity_user = result.scalar_one_or_none()
                finally:
                    result.close()
        except Exception as e:
            self.logger.error(f"查询业务用户失败: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content=error_response(message="服务异常，请稍后重试", code=ErrorCodes.INTERNAL_ERROR).model_dump(),
            )

        if identity_user is None:
            return JSONResponse(
                status_code=401,
                content=error_response(message="Token 已失效", code=ErrorCodes.INVALID_TOKEN).model_dump(),
            )

        request.state.current_user_info = current_user_info  # 整个请求周期可访问
        return await call_next(request)
