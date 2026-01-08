from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ChatbotMessageItem(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    type: str = Field(default="text", min_length=1)
    content: str = Field(..., min_length=1)
    meta: Optional[Dict[str, Any]] = None


class ChatbotMessageTask(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        alias_generator=_to_camel,
        populate_by_name=True,
    )

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


class ChatbotDispatchResult(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    count: int = Field(..., description="Number of tasks published")


class OutreachChatbotTask(BaseModel):
    """Outreach chatbot task payload (message content decided by chatbot)."""

    model_config = ConfigDict(
        extra="allow",
        alias_generator=_to_camel,
        populate_by_name=True,
    )

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


class OutreachChatbotControlRequest(BaseModel):
    """Control message to start/stop per-task outreach chatbot consumer."""

    model_config = ConfigDict(
        extra="allow",
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    action: Literal["start", "end"] = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
