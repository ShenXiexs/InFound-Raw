import re

from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from apps.portal_creator_open_api.core.deps import get_token_manager, get_settings
from core_base import get_logger


class AuthFilterMiddleware(BaseHTTPMiddleware):
    """
    身份验证中间件：
    利用 TokenManager 类单例进行统一鉴权
    """

    def __init__(self, app: FastAPI):
        super().__init__(app)
        self.logger = get_logger("AuthFilterMiddleware")

    # 建议将排除路径正则化或提取到配置中
    EXCLUDE_PATH_PATTERNS = [
        r"^/account/login$",
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

        # 2. 从 Header 获取 Token
        token = request.headers.get(settings.auth.required_header)
        if not token:
            return self._unauthorized("AccessToken missing")

        # 3. 解析 Token (调用 TokenManager 类方法)
        payload = token_manager.decode_access_token(token)
        if not payload:
            return self._unauthorized("Invalid or expired token")

        username = payload.get("sub")
        jti = payload.get("jti")

        if not username or not jti:
            return self._unauthorized("Malformed token payload")

        # 4. 核心优化：一次性从 Redis 获取用户信息并验证
        # 如果 Redis 中没有这个 JTI，说明已登出或被踢下线
        user_info = token_manager.get_current_user_info(username, jti)
        if not user_info:
            self.logger.warning(
                f"Unauthorized access attempt: user={username}, jti={jti}"
            )
            return self._unauthorized("Session expired or logged out")

        # 5. 存入 request.state 供后续逻辑使用
        request.state.current_user_info = user_info

        # 6. 继续后续请求
        return await call_next(request)

    def _unauthorized(self, message: str) -> JSONResponse:
        """统一的未授权响应格式"""
        return JSONResponse(
            status_code=401, content={"detail": message, "code": "UNAUTHORIZED"}
        )
