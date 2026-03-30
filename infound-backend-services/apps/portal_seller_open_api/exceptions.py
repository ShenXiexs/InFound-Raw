from typing import Optional, Dict, Any

from core_web.exceptions import AppException


# ====================
# 通用异常基类
# ====================
class PortalSellerError(AppException):
    """Portal Seller 业务异常基类"""
    default_status_code = 400
    default_business_code = 400

    def __init__(
            self,
            message: Optional[str] = None,
            status_code: Optional[int] = None,
            business_code: Optional[int] = None,
            extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            business_code=business_code,
            extra=extra
        )


# ====================
# 常用异常类（5 个，覆盖 90% 场景）
# ====================
class ValidationError(PortalSellerError):
    """参数验证错误 (400)"""
    default_message = "参数验证失败"
    default_business_code = 400


class UnauthorizedError(PortalSellerError):
    """未授权 (401)"""
    default_message = "未授权访问"
    default_status_code = 401
    default_business_code = 401


class NotFoundError(PortalSellerError):
    """资源不存在 (404)"""
    default_message = "资源不存在"
    default_status_code = 404
    default_business_code = 404


class ForbiddenError(PortalSellerError):
    """禁止访问 (403)"""
    default_message = "权限不足"
    default_status_code = 403
    default_business_code = 403


class ServerError(PortalSellerError):
    """服务器错误 (500)"""
    default_message = "服务器内部错误"
    default_status_code = 500
    default_business_code = 500


# ====================
# 错误码常量类（查表用，IDE 有补全）
# ====================
class ErrorCodes:
    """错误码常量类"""

    # 通用错误
    BAD_REQUEST = 400
    INTERNAL_ERROR = 500

    # 账号相关 (12xx)
    MISSING_DEVICE_ID = 1208
    INVALID_PHONE_NUMBER = 400
    VERIFICATION_CODE_EXPIRED = 1207
    VERIFICATION_CODE_INVALID = 1202
    SMS_SEND_LIMIT_EXCEEDED = 1206
    REGISTRATION_FAILED = 500
    LOGIN_FAILED = 500
    USER_NOT_FOUND = 1204
    INVALID_PASSWORD = 1203
    USER_ALREADY_EXISTS = 1201
    PHONE_ALREADY_REGISTERED = 1201

    # Token 相关 (125x)
    INVALID_TOKEN = 1251
    MISSING_ACCESS_TOKEN = 401
    TOKEN_LOGGED_OUT = 401


# ====================
# 快捷工厂函数（记不住类名时用这个）
# ====================
def raise_error(
        message: str = "业务异常",
        code: int = 400,
        status_code: int = 400,
        extra: Optional[Dict[str, Any]] = None
):
    """
    抛出业务异常（统一入口）

    Args:
        message: 错误消息
        code: 业务错误码
        status_code: HTTP 状态码
        extra: 额外数据

    Raises:
        PortalSellerError
    """
    raise PortalSellerError(
        message=message,
        status_code=status_code,
        business_code=code,
        extra=extra or {}
    )


def raise_account_error(message: str, code: int):
    """抛出账号相关异常"""
    raise_error(message=message, code=code, status_code=400)


def raise_sms_error(message: str, code: int):
    """抛出短信相关异常"""
    raise_error(message=message, code=code, status_code=400)


def raise_token_error(message: str, code: int):
    """抛出 Token 相关异常"""
    raise_error(message=message, code=code, status_code=401)


def raise_user_error(message: str, code: int):
    """抛出用户相关异常"""
    raise_error(message=message, code=code, status_code=400)
