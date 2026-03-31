from fastapi import APIRouter, Depends

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.core.deps import get_settings
from apps.portal_seller_open_api.core.rabbitmq_producer import RabbitMQProducer
from apps.portal_seller_open_api.models.dtos.ws_notification_dto import SendNotificationResponse, \
    SendNotificationRequest
from core_base import APIResponse, success_response, get_logger, error_response

router = APIRouter(tags=["首页"])
logger = get_logger(__name__)


@router.get(
    "/",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def home():
    """首页"""
    return success_response(data={"message": "XunDa Open API"})


@router.post(
    "/test/notification/send",
    response_model=APIResponse[SendNotificationResponse],
    summary="发送测试通知",
    description="向指定用户发送测试通知消息",
)
async def test_send_notification(
        request: SendNotificationRequest,
        settings: Settings = Depends(get_settings),
) -> APIResponse[SendNotificationResponse]:
    """
    发送测试通知到指定用户的队列

    用于测试用户通知功能，实际使用时请替换为业务逻辑调用
    """
    try:
        if not RabbitMQProducer.is_initialized():
            await RabbitMQProducer.initialize(settings.rabbitmq_web_stomp)

        publish_result = await RabbitMQProducer.publish_user_notification_message(
            user_id=request.user_id,
            title=request.title,
            content=request.content,
            message_type=request.message_type,
        )

        return success_response(
            data=SendNotificationResponse(
                message_id=publish_result["message_id"],
                user_id=request.user_id,
                status="sent",
            ),
            message="测试通知已发送",
        )

    except Exception as e:
        logger.error(f"Failed to send test notification: {e}", exc_info=True)
        return error_response(
            message=f"发送通知失败：{str(e)}",
            code=500,
        )
