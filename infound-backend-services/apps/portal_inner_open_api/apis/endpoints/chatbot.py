from typing import List

from fastapi import APIRouter, HTTPException, status

from common.core.response import APIResponse, success_response
from common.services.rabbitmq_producer import RabbitMQProducer
from apps.portal_inner_open_api.models.chatbot import (
    ChatbotDispatchResult,
    ChatbotMessageTask,
)

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])


@router.post(
    "/messages",
    response_model=APIResponse[ChatbotDispatchResult],
    response_model_by_alias=True,
)
async def publish_chatbot_messages(
    payload: List[ChatbotMessageTask],
) -> APIResponse[ChatbotDispatchResult]:
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty tasks array",
        )

    tasks = [task.model_dump(by_alias=True, exclude_none=True) for task in payload]
    try:
        for task in tasks:
            await RabbitMQProducer.publish_batch_chatbot_messages([task])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to publish chatbot messages: {exc}",
        ) from exc

    return success_response(ChatbotDispatchResult(count=len(tasks)))
