from typing import List

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from common.core.config import get_settings
from common.core.logger import get_logger

settings = get_settings()
logger = get_logger()


class RequestFilterMiddleware(BaseHTTPMiddleware):
    # --------------------------
    # 2. 豁免接口配置
    # --------------------------
    exempt_paths = [
        "/",
        "/health",  # 健康检查接口
    ]

    async def dispatch(self, request, call_next):
        # 豁免接口直接放行
        logger.info(f"请求路径：{request.url.path}")

        if any(request.url.path.startswith(path) for path in self.exempt_paths):
            response = await call_next(request)
            return response

        # 1. 从 Header 中获取 Token
        required_header = settings.AUTH__REQUIRED_HEADER
        token = request.headers.get(required_header)

        # 2. 校验 Token
        if not token:
            logger.warning(f"缺少 Header：{required_header}")
            return JSONResponse(
                status_code=401,
                content={"detail": f"Unauthorized: 缺少 Header '{required_header}'"}
            )

        valid_tokens: List[str] = settings.AUTH__VALID_TOKENS
        if token not in valid_tokens:
            logger.warning(f"非法 Token：{token}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: 无效的 Token"}
            )

        # 3. Token 合法，继续执行请求
        logger.info(f"Token 校验通过：{token}")
        response = await call_next(request)
        return response
