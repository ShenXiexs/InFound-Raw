from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from apps.portal_creator_open_api.services.security import decode_access_token, is_token_valid_in_redis, \
    get_current_user_info
from common import app_constants
from common.core.config import get_settings
from common.core.logger import get_logger

settings = get_settings()
logger = get_logger()


class AuthFilterMiddleware(BaseHTTPMiddleware):
    """
    身份验证中间件：
    1. 检查 Header 中的 AccessToken
    2. 验证 Token 有效性及 Redis 存在性
    3. 将用户信息存入 request.state，供后续请求使用
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        # 排除不需要验证的路径（如登录、文档等）
        exclude_paths = ["/account/login", "/", "/docs", "/redoc", "/openapi.json"]
        if request.url.path in exclude_paths:
            return await call_next(request)

        # 1. 获取 Header 中的 AccessToken
        token = request.headers.get(app_constants.CREATOR_ACCESS_TOKEN_HEADER)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "No AccessToken"}
            )

        # 2. 验证 Token 并解析用户信息
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid AccessToken")
        username: str = payload.get("sub")
        token_jti: str = payload.get("jti")
        if not username or not token_jti:
            raise HTTPException(status_code=401, detail="Invalid AccessToken")

        # 3. 检查 Token 是否在 Redis 中（未被登出）
        if not is_token_valid_in_redis(username, token_jti):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid AccessToken (logged out or exceeded the limit)"}
            )

        # 4. 构建用户对象并存入 request.state
        user = get_current_user_info(username, token_jti)
        request.state.current_user_info = user  # 整个请求周期可访问

        # 继续处理请求
        response = await call_next(request)
        return response
