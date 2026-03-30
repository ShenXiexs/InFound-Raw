from pydantic import Field

from shared_application_services import BaseDTO


class SendNotificationRequest(BaseDTO):
    """发送测试通知请求"""
    user_id: str = Field(..., description="目标用户 ID")
    title: str = Field(..., description="消息标题", min_length=1, max_length=100)
    content: str = Field(..., description="消息内容", min_length=1, max_length=500)
    message_type: str = Field(
        default="notification",
        description="消息类型：notification/order/system",
    )


class SendNotificationResponse(BaseDTO):
    """发送测试通知响应"""
    message_id: str
    user_id: str
    status: str
