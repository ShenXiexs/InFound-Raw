from __future__ import annotations

from typing import Any, Dict, List, Optional

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
