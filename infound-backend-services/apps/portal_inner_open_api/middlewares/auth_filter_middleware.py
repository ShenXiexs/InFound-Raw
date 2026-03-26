import re
from typing import List

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from apps.portal_inner_open_api.core.deps import get_settings
from core_base import get_logger


class AuthFilterMiddleware(BaseHTTPMiddleware):

    def __init__(self, app: FastAPI):
        super().__init__(app)
        self.logger = get_logger()

    EXCLUDE_PATH_PATTERNS = [
        r"^/health$",
        r"^/$",
        r"^/docs.*",
        r"^/redoc.*",
        r"^/openapi.json$",
    ]

    async def dispatch(self, request, call_next):
        # 豁免接口直接放行
        self.logger.info(f"请求路径：{request.url.path}")

        # 1. 排除不需要验证的路径
        if any(re.match(pattern, request.url.path) for pattern in self.EXCLUDE_PATH_PATTERNS):
            return await call_next(request)

        settings = get_settings(request)

        # 1. 从 Header 中获取 Token
        required_header = settings.auth.required_header
        token = request.headers.get(required_header)

        # 2. 校验 Token
        if not token:
            self.logger.warning(f"缺少 Header：{required_header}")
            return JSONResponse(
                status_code=401,
                content={"detail": f"Unauthorized: 缺少 Header '{required_header}'"},
            )

        valid_tokens: List[str] = [settings.auth.secret_key]
        if token not in valid_tokens:
            self.logger.warning(f"非法 Token：{token}")
            return JSONResponse(
                status_code=401, content={"detail": "Unauthorized: 无效的 Token"}
            )

        # 3. Token 合法，继续执行请求
        self.logger.info(f"Token 校验通过：{token}")
        response = await call_next(request)
        return response
