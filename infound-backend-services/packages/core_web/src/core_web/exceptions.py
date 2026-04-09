from typing import Dict, Any, Optional

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse

from core_base import get_logger, error_response


# --- 1. 增强型异常基类 ---
class AppException(Exception):
    """
    自定义业务异常基类
    default_code: 业务自定义状态码 (e.g., 10001)
    status_code:  HTTP 状态码 (e.g., 400)
    """

    default_message: str = "业务异常"
    default_status_code: int = status.HTTP_400_BAD_REQUEST
    default_business_code: int = 400

    def __init__(
            self,
            message: Optional[str] = None,
            status_code: Optional[int] = None,
            business_code: Optional[int] = None,
            extra: Optional[Dict[str, Any]] = None,
    ):
        self.message = message or self.default_message
        self.status_code = status_code or self.default_status_code
        self.business_code = business_code or self.default_business_code
        self.extra = extra or {}
        super().__init__(self.message)


# --- 2. 业务异常子类 (更简洁的定义方式) ---
class ResourceNotFoundError(AppException):
    default_message = "资源不存在"
    default_status_code = status.HTTP_404_NOT_FOUND
    default_business_code = 404


class PermissionDeniedError(AppException):
    default_message = "权限不足"
    default_status_code = status.HTTP_403_FORBIDDEN
    default_business_code = 403


class InitializationError(AppException):
    default_message = "初始化失败"
    default_status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_business_code = 500
    pass


# --- 3. 异常处理器管理类 ---
class ExceptionHandlerRegistry:
    """
    统一注册和管理 FastAPI 异常处理器的类
    """

    logger = get_logger(__name__)

    @classmethod
    async def handle_app_exception(
            cls, request: Request, exc: AppException
    ) -> JSONResponse:
        """处理业务应用异常"""
        # 安全地解包 extra，避免键冲突
        log_context = {
            "path": request.url.path,
            "method": request.method,
            "business_code": exc.business_code,
        }
        if exc.extra:
            log_context.update(exc.extra)

        log = cls.logger.bind(**log_context)
        log.warning(
            "business_exception", message=exc.message
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(
                message=exc.message, code=exc.business_code, data=exc.extra
            ).model_dump(),
        )

    @classmethod
    async def handle_http_exception(
            cls, request: Request, exc: HTTPException
    ) -> JSONResponse:
        """处理 FastAPI HTTPException（兼容旧代码）"""
        # 从 detail 获取消息，status_code 作为 business_code
        message = exc.detail if hasattr(exc, 'detail') else "HTTP 错误"
        status_code = exc.status_code if hasattr(exc, 'status_code') else 400

        cls.logger.warning(
            "http_exception",
            path=request.url.path,
            method=request.method,
            status_code=status_code,
            message=message
        )

        return JSONResponse(
            status_code=status_code,
            content=error_response(
                message=message, code=status_code
            ).model_dump(),
        )

    @classmethod
    async def handle_validation_error(
            cls, request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """处理参数校验异常"""
        error_details = [
            {
                "location": ".".join(map(str, err["loc"][1:])),
                "msg": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]

        cls.logger.error(
            "validation_error", path=request.url.path, errors=error_details
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response(
                message="参数校验失败",
                code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                data={"details": error_details},
            ).model_dump(),
        )

    @classmethod
    async def handle_global_exception(
            cls, request: Request, exc: Exception
    ) -> JSONResponse:
        """处理全局未捕获异常（500 错误）"""
        # 针对 500 错误，记录详细的堆栈信息
        cls.logger.exception(
            "未处理异常", path=request.url.path, error=str(exc)
        )

        # 区分开发环境和生产环境的显示
        is_debug = getattr(request.app.state, "debug", False)
        msg = (
            f"服务器内部错误：{str(exc)}" if is_debug else "服务暂时不可用，请稍后再试"
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                message=msg, code=status.HTTP_500_INTERNAL_SERVER_ERROR
            ).model_dump(),
        )

    @classmethod
    def register(cls, app) -> None:
        """
        注册所有异常处理器到 FastAPI 应用

        Args:
            app: FastAPI 应用实例
        """
        app.add_exception_handler(AppException, cls.handle_app_exception)
        app.add_exception_handler(HTTPException, cls.handle_http_exception)
        app.add_exception_handler(RequestValidationError, cls.handle_validation_error)
        app.add_exception_handler(Exception, cls.handle_global_exception)


# 保持向后兼容的快捷函数
def register_exception_handlers(app):
    """注册所有异常处理器（兼容旧版本）"""
    ExceptionHandlerRegistry.register(app)
