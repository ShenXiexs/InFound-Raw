from typing import Dict, Any, Optional

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse

from common.core.logger import get_logger
from common.core.response import error_response

logger = get_logger(__name__)


# 自定义异常基类
class AppException(Exception):
    def __init__(self, message: str, code: int = 400, extra: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.extra = extra or {}
        super().__init__(self.message)


# 业务异常示例
class ResourceNotFoundError(AppException):
    def __init__(self, resource: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(message=f"{resource} 不存在", code=status.HTTP_404_NOT_FOUND, extra=extra)


class PermissionDeniedError(AppException):
    def __init__(self, extra: Optional[Dict[str, Any]] = None):
        super().__init__(message="权限不足", code=status.HTTP_403_FORBIDDEN, extra=extra)


class RabbitMQConnectionError(Exception):
    pass


class MessageProcessingError(Exception):
    pass


# 全局异常处理器
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """自定义业务异常处理器"""
    extra = {
        "request_path": request.url.path,
        "request_method": request.method,
        "status_code": exc.code,
        **exc.extra
    }
    logger.warning(f"业务异常: {exc.message}", extra=extra)
    return JSONResponse(
        status_code=exc.code,
        content=error_response(message=exc.message, code=exc.code, data=exc.extra).model_dump()
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTP 异常处理器"""
    extra = {
        "request_path": request.url.path,
        "request_method": request.method,
        "status_code": exc.status_code,
        "detail": str(exc.detail)
    }
    logger.warning(f"HTTP异常: {exc.detail}", extra=extra)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(message=str(exc.detail), code=exc.status_code).model_dump()
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """参数验证异常处理器"""
    error_details = []
    for err in exc.errors():
        field = ".".join(str(item) for item in err["loc"][1:])  # 排除 "body" 前缀
        error_details.append(f"{field}: {err['msg']}")

    extra = {
        "request_path": request.url.path,
        "request_method": request.method,
        "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "errors": error_details
    }
    logger.error("参数验证异常", extra=extra)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response(
            message="参数验证失败",
            code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            data={"details": error_details}
        ).model_dump()
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局未捕获异常处理器"""
    extra = {
        "request_path": request.url.path,
        "request_method": request.method,
        "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "error": str(exc)
    }
    logger.error("未捕获异常", exc_info=True, extra=extra)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            message="服务器内部错误" if request.app.state.debug else "服务异常，请联系管理员",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR
        ).model_dump()
    )


# 注册所有异常处理器
def register_exception_handlers(app):
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
