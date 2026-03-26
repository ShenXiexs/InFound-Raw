from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal

from pydantic import Field

from shared_application_services import BaseDTO


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ChatbotMessageItem(BaseDTO):
    type: str = Field(default="text", min_length=1)
    content: str = Field(..., min_length=1)
    meta: Optional[Dict[str, Any]] = None


class ChatbotMessageTask(BaseDTO):
    region: Optional[str] = None
    platform_creator_id: str = Field(..., min_length=1)
    messages: List[ChatbotMessageItem] = Field(..., min_length=1)
    account_name: Optional[str] = None
    sender_id: Optional[str] = Field(default=None, alias="from")
    operator_id: Optional[str] = None
    sample_id: Optional[str] = None
    platform_product_id: Optional[str] = None
    platform_product_name: Optional[str] = None
    platform_campaign_name: Optional[str] = None
    platform_creator_username: Optional[str] = None
    creator_whatsapp: Optional[str] = None


class ChatbotDispatchResult(BaseDTO):
    count: int = Field(..., description="Number of tasks published")


class OutreachChatbotTask(BaseDTO):
    task_id: Optional[str] = None
    outreach_task_id: Optional[str] = None
    region: Optional[str] = None
    platform_creator_id: str = Field(..., min_length=1)
    platform_creator_username: Optional[str] = None
    platform_creator_display_name: Optional[str] = None
    creator_name: Optional[str] = None
    creator_username: Optional[str] = None
    account_name: Optional[str] = None
    operator_id: Optional[str] = None
    brand_name: Optional[str] = None
    only_first: Optional[Any] = None
    task_metadata: Optional[Dict[str, Any]] = None


class OutreachChatbotControlRequest(BaseDTO):
    action: Literal["start", "end"] = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
