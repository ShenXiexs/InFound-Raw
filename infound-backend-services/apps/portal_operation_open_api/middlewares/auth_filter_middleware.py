import re

from fastapi import HTTPException, Request, FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from apps.portal_operation_open_api.core.deps import get_token_manager, get_settings
from core_base import get_logger


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
        r"^/auth/login$",
        r"^/$",
        r"^/docs.*",
        r"^/redoc.*",
        r"^/openapi.json$",
    ]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        path = request.url.path

        # 1. 排除不需要验证的路径
        if any(re.match(pattern, path) for pattern in self.EXCLUDE_PATH_PATTERNS):
            return await call_next(request)

        settings = get_settings(request)
        token_manager = get_token_manager(request)

        # 1. 获取 Header 中的 AccessToken
        token = request.headers.get(settings.auth.required_header)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "No AccessToken"}
            )

        # 2. 验证 Token 并解析用户信息
        payload = token_manager.decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid AccessToken")
        username: str = payload.get("sub")
        token_jti: str = payload.get("jti")
        if not username or not token_jti:
            raise HTTPException(status_code=401, detail="Invalid AccessToken")

        # 3. 检查 Token 是否在 Redis 中（未被登出）
        if not token_manager.is_token_valid_in_redis(username, token_jti):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid AccessToken (logged out or exceeded the limit)"}
            )

        # 4. 构建用户对象并存入 request.state
        user = token_manager.get_current_user_info(username, token_jti)
        if not user:
            raise HTTPException(status_code=401, detail="User info not found")

        request.state.current_user_info = user  # 整个请求周期可访问

        # 继续处理请求
        return await call_next(request)
