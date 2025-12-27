from typing import List

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from common.core.config import get_settings
from common.core.logger import get_logger

settings = get_settings()
logger = get_logger()


class RequestFilterMiddleware(BaseHTTPMiddleware):
    # --------------------------
    # 2. Exempt endpoints
    # --------------------------
    exempt_paths = [
        "/",
        "/health",  # health check
    ]

    async def dispatch(self, request, call_next):
        # Allow exempt paths
        logger.info(f"Request path: {request.url.path}")

        if any(request.url.path.startswith(path) for path in self.exempt_paths):
            response = await call_next(request)
            return response

        # 1. Read token from header
        required_header = settings.AUTH__REQUIRED_HEADER
        token = request.headers.get(required_header)

        # 2. Validate token
        if not token:
            logger.warning(f"Missing header: {required_header}")
            return JSONResponse(
                status_code=401,
                content={"detail": f\"Unauthorized: missing header '{required_header}'\"}
            )

        valid_tokens: List[str] = settings.AUTH__VALID_TOKENS
        if token not in valid_tokens:
            logger.warning(f"Invalid token: {token}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: invalid token"}
            )

        # 3. Token valid, continue
        logger.info(f"Token validated: {token}")
        response = await call_next(request)
        return response
