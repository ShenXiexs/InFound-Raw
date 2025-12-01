"""
自定义异常
"""

class APIException(Exception):
    """API基础异常"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class AuthenticationError(APIException):
    """认证异常"""
    def __init__(self, message: str = "认证失败"):
        super().__init__(message, status_code=401)

class PermissionError(APIException):
    """权限异常"""
    def __init__(self, message: str = "权限不足"):
        super().__init__(message, status_code=403)

class NotFoundError(APIException):
    """资源不存在异常"""
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, status_code=404)
