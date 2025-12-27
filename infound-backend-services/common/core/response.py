from typing import Generic, TypeVar, Optional, Any

from pydantic import BaseModel

# Generic type variable
T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Unified API response schema."""
    code: int = 200
    msg: str = "success"
    data: Optional[T] = None

    # request_id: Optional[str] = None  # optional request ID (tracing)

    class Config:
        arbitrary_types_allowed = True


# Convenience response helpers
def success_response(data: Optional[T] = None, message: str = "success", code: int = 200) -> APIResponse[T]:
    return APIResponse(code=code, msg=message, data=data)


def error_response(message: str = "error", code: int = 400, data: Optional[Any] = None) -> APIResponse[Any]:
    return APIResponse(code=code, msg=message, data=data)
