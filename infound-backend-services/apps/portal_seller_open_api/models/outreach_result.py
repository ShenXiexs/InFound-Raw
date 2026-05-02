from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from shared_application_services import BaseDTO


class OutreachCreatorResultItem(BaseDTO):
    platform_creator_id: Optional[str] = None
    creator_id: Optional[str] = None
    creator_name: Optional[str] = None
    avatar_url: Optional[str] = None
    category: Optional[str] = None
    send: Optional[Any] = None
    is_new: Optional[Any] = None
    send_time: Optional[Any] = None


class OutreachResultIngestionRequest(BaseDTO):
    task_id: str = Field(..., min_length=1)
    shop_id: str = Field(..., min_length=1)
    new_count: Optional[Any] = None
    spend_time: Optional[Any] = None
    started_at: Optional[Any] = None
    finished_at: Optional[Any] = None
    creators: list[OutreachCreatorResultItem] = Field(default_factory=list)


class OutreachResultIngestionResult(BaseDTO):
    task_id: str
    inserted_task_logs: int
    updated_creator_counts: int
    real_count: int
    new_count: int
