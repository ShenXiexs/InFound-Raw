import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from apps.portal_seller_open_api.core.deps import get_settings, get_token_manager
from core_base import get_logger


class AuthFilterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI):
        super().__init__(app)
        self.logger = get_logger()

    EXCLUDE_PATH_PATTERNS = [
        r"^/$",
        r"^/docs.*",
        r"^/redoc.*",
        r"^/openapi.json$",
    ]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        path = request.url.path
        if any(re.match(pattern, path) for pattern in self.EXCLUDE_PATH_PATTERNS):
            return await call_next(request)

        settings = get_settings(request)
        token_manager = get_token_manager(request)

        token = request.headers.get(settings.auth.required_header)
        if not token:
            return JSONResponse(status_code=401, content={"detail": "No AccessToken"})

        payload = token_manager.decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid AccessToken")

        username = payload.get("sub")
        token_jti = payload.get("jti")
        if not username or not token_jti:
            raise HTTPException(status_code=401, detail="Invalid AccessToken")

        if not token_manager.is_token_valid_in_redis(username, token_jti):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid AccessToken (logged out or exceeded the limit)"},
            )

        user = token_manager.get_current_user_info(username, token_jti)
        if not user:
            raise HTTPException(status_code=401, detail="User info not found")

        request.state.current_user_info = user
        return await call_next(request)
