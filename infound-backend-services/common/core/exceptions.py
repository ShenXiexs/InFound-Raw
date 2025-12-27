from typing import Dict, Any, Optional

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse

from common.core.logger import get_logger
from common.core.response import error_response

logger = get_logger(__name__)


# Base custom exception
class AppException(Exception):
    def __init__(self, message: str, code: int = 400, extra: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.extra = extra or {}
        super().__init__(self.message)


# Domain-specific exceptions
class ResourceNotFoundError(AppException):
    def __init__(self, resource: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(message=f"{resource} not found", code=status.HTTP_404_NOT_FOUND, extra=extra)


class PermissionDeniedError(AppException):
    def __init__(self, extra: Optional[Dict[str, Any]] = None):
        super().__init__(message="Insufficient permissions", code=status.HTTP_403_FORBIDDEN, extra=extra)


# Global exception handlers
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Custom domain exception handler."""
    extra = {
        "request_path": request.url.path,
        "request_method": request.method,
        "status_code": exc.code,
        **exc.extra
    }
    logger.warning(f"App exception: {exc.message}", extra=extra)
    return JSONResponse(
        status_code=exc.code,
        content=error_response(message=exc.message, code=exc.code, data=exc.extra).model_dump()
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTP exception handler."""
    extra = {
        "request_path": request.url.path,
        "request_method": request.method,
        "status_code": exc.status_code,
        "detail": str(exc.detail)
    }
    logger.warning(f"HTTP exception: {exc.detail}", extra=extra)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(message=str(exc.detail), code=exc.status_code).model_dump()
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Request validation exception handler."""
    error_details = []
    for err in exc.errors():
        field = ".".join(err["loc"][1:])  # drop the "body" prefix
        error_details.append(f"{field}: {err['msg']}")

    extra = {
        "request_path": request.url.path,
        "request_method": request.method,
        "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "errors": error_details
    }
    logger.error("Validation error", extra=extra)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response(
            message="Validation failed",
            code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            data={"details": error_details}
        ).model_dump()
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler."""
    extra = {
        "request_path": request.url.path,
        "request_method": request.method,
        "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "error": str(exc)
    }
    logger.error("Unhandled exception", exc_info=True, extra=extra)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            message="Internal server error" if request.app.state.debug else "Service error; contact support",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR
        ).model_dump()
    )


# Register all exception handlers
def register_exception_handlers(app):
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
