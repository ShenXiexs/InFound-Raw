from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class OutreachTaskPayload(BaseModel):
    """Normalized outreach task payload from the crawler."""

    model_config = ConfigDict(
        extra="allow",
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_id: Optional[str] = None
    platform: Optional[str] = None
    task_name: Optional[str] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    product_list: Optional[Any] = None
    region: Optional[str] = None
    brand: Optional[str] = None
    only_first: Optional[Any] = None
    task_type: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    account_email: Optional[str] = None
    search_keywords: Optional[str] = None
    product_category: Optional[Any] = None
    fans_age_range: Optional[Any] = None
    fans_gender: Optional[Any] = None
    content_type: Optional[Any] = None
    gmv: Optional[Any] = None
    sales: Optional[Any] = None
    min_fans: Optional[Any] = None
    avg_views: Optional[Any] = None
    min_avg_views: Optional[Any] = None
    min_engagement_rate: Optional[Any] = None
    email_first_body: Optional[str] = None
    email_later_body: Optional[str] = None
    target_new_creators: Optional[Any] = None
    max_creators: Optional[Any] = None
    run_at_time: Optional[Any] = None
    run_end_time: Optional[Any] = None
    run_time: Optional[Any] = None
    new_creators: Optional[Any] = None
    started_at: Optional[Any] = None
    finished_at: Optional[Any] = None
    created_at: Optional[Any] = None


class OutreachTaskIngestionRequest(BaseModel):
    """Request body used to upsert an outreach task."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    source: Optional[str] = Field(default=None, description="Data source identifier")
    operator_id: Optional[str] = Field(
        default=None, description="Operator/account ID used for audit fields"
    )
    task: OutreachTaskPayload


class OutreachTaskIngestionResult(BaseModel):
    """Response payload returned to the collector."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_id: str = Field(..., description="Outreach task ID")


class OutreachTaskProgressRequest(BaseModel):
    """Request body used to increment outreach task progress."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_id: str = Field(..., min_length=1)
    delta: int = Field(default=1, ge=1)
    operator_id: Optional[str] = None


class OutreachTaskProgressResult(BaseModel):
    """Response payload returned after progress update."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_id: str
    new_creators_real_count: int
