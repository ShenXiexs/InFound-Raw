from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class CreatorIngestionOptions(BaseModel):
    """Metadata describing the creator crawl task."""

    model_config = ConfigDict(
        extra="allow",
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_id: Optional[str] = None
    account_name: Optional[str] = None
    region: Optional[str] = None
    brand_name: Optional[str] = None
    search_strategy: Optional[Dict[str, Any]] = None


class CreatorRow(BaseModel):
    """Normalized creator row produced by the crawler."""

    model_config = ConfigDict(
        extra="allow",
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    platform: Optional[str] = None
    platform_creator_id: Optional[str] = None
    platform_creator_username: Optional[str] = None
    platform_creator_display_name: Optional[str] = None
    creator_id: Optional[str] = None
    creator_name: Optional[str] = None
    creator_username: Optional[str] = None
    creator_chaturl: Optional[str] = None
    search_keywords: Optional[str] = None
    brand_name: Optional[str] = None
    region: Optional[str] = None
    currency: Optional[str] = None
    categories: Optional[str] = None
    followers: Optional[Any] = None
    intro: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    sales_revenue: Optional[Any] = None
    sales_units_sold: Optional[Any] = None
    sales_gpm: Optional[Any] = None
    sales_revenue_per_buyer: Optional[Any] = None
    gmv_per_sales_channel: Optional[str] = None
    gmv_by_product_category: Optional[str] = None
    avg_commission_rate: Optional[Any] = None
    collab_products: Optional[Any] = None
    partnered_brands: Optional[Any] = None
    product_price: Optional[str] = None
    video_gpm: Optional[Any] = None
    videos: Optional[Any] = None
    avg_video_views: Optional[Any] = None
    avg_video_engagement_rate: Optional[Any] = None
    avg_video_likes: Optional[Any] = None
    avg_video_comments: Optional[Any] = None
    avg_video_shares: Optional[Any] = None
    live_gpm: Optional[Any] = None
    live_streams: Optional[Any] = None
    avg_live_views: Optional[Any] = None
    avg_live_engagement_rate: Optional[Any] = None
    avg_live_likes: Optional[Any] = None
    avg_live_comments: Optional[Any] = None
    avg_live_shares: Optional[Any] = None
    followers_male: Optional[Any] = None
    followers_female: Optional[Any] = None
    followers_18_24: Optional[Any] = None
    followers_25_34: Optional[Any] = None
    followers_35_44: Optional[Any] = None
    followers_45_54: Optional[Any] = None
    followers_55_more: Optional[Any] = None
    connect: Optional[Any] = None
    reply: Optional[Any] = None
    send: Optional[Any] = None
    send_time: Optional[str] = None
    top_brands: Optional[str] = None
    crawl_date: Optional[str] = None


class CreatorIngestionRequest(BaseModel):
    """Request body that collector posts to the inner API."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    source: str = Field(..., description="Data source identifier")
    operator_id: Optional[str] = Field(
        default=None,
        description="Operator/account ID used for audit fields",
    )
    options: Optional[CreatorIngestionOptions] = None
    rows: List[CreatorRow] = Field(..., min_length=1)


class CreatorIngestionResult(BaseModel):
    """Response payload returned to the collector."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    inserted: int = Field(..., description="Total creator rows ingested")
    creators: int = Field(..., description="Unique creators updated")


class CreatorHistoryRequest(BaseModel):
    """Query params for creator history lookups."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    creator_id: Optional[str] = None
    creator_name: Optional[str] = None
    creator_username: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=200)


class CreatorHistoryItem(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    connect: bool
    reply: bool
    brand_name: Optional[str] = None


class CreatorHistoryResult(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    records: List[CreatorHistoryItem]
