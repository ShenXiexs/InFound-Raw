from typing import Generic, TypeVar, Optional, Any

from pydantic import BaseModel

# 泛型类型变量
T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""
    code: int = 200
    msg: str = "success"
    data: Optional[T] = None
    request_id: Optional[str] = None  # 可选：请求ID（用于追踪）

    class Config:
        arbitrary_types_allowed = True


# 快捷响应函数
def success_response(data: Optional[T] = None, message: str = "success", code: int = 200) -> APIResponse[T]:
    return APIResponse(code=code, msg=message, data=data)


def error_response(message: str = "error", code: int = 400, data: Optional[Any] = None) -> APIResponse[Any]:
    return APIResponse(code=code, msg=message, data=data)
