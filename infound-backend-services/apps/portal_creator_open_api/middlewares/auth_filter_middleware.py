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
    Authentication middleware:
    1. Extract AccessToken from headers.
    2. Validate the token and ensure it exists in Redis.
    3. Store user info in request.state for downstream handlers.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        # Paths that skip authentication (login/docs/etc.)
        exclude_paths = ["/account/login", "/", "/docs", "/redoc", "/openapi.json"]
        if request.url.path in exclude_paths:
            return await call_next(request)

        # 1) Read AccessToken from header
        token = request.headers.get(app_constants.CREATOR_ACCESS_TOKEN_HEADER)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "No AccessToken"}
            )

        # 2) Validate token and parse user info
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid AccessToken")
        username: str = payload.get("sub")
        token_jti: str = payload.get("jti")
        if not username or not token_jti:
            raise HTTPException(status_code=401, detail="Invalid AccessToken")

        # 3) Ensure the token still exists in Redis (not logged out/expired)
        if not is_token_valid_in_redis(username, token_jti):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid AccessToken (logged out or exceeded the limit)"}
            )

        # 4) Build user object and store it on request.state
        user = get_current_user_info(username, token_jti)
        request.state.current_user_info = user  # accessible for the entire request

        # Continue request
        response = await call_next(request)
        return response
