from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class SampleIngestionOptions(BaseModel):
    """Metadata describing the crawl task options."""

    model_config = ConfigDict(
        extra="allow",
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    campaign_id: Optional[str] = None
    campaign_ids: Optional[List[str]] = None
    account_name: Optional[str] = None
    region: Optional[str] = None
    tabs: Optional[List[str]] = None
    expand_view_content: Optional[bool] = None
    max_pages: Optional[int] = None
    scan_all_pages: Optional[bool] = None
    export_excel: Optional[bool] = None
    view_logistics: Optional[bool] = None
    manual_login: Optional[bool] = None


class SampleRow(BaseModel):
    """Normalized row produced by the crawler."""

    model_config = ConfigDict(
        extra="allow",
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    platform_product_id: str = Field(..., min_length=1)
    region: Optional[str] = None
    product_name: Optional[str] = None
    platform_campaign_id: Optional[str] = None
    platform_campaign_name: Optional[str] = None
    product_sku: Optional[str] = None
    stock: Optional[int] = None
    available_sample_count: Optional[int] = None
    is_uncooperative: Optional[int] = None
    is_unapprovable: Optional[int] = None
    status: Optional[str] = None
    request_time_remaining: Optional[str] = None
    platform_creator_display_name: Optional[str] = None
    platform_creator_username: Optional[str] = None
    platform_creator_id: Optional[str] = None
    creator_url: Optional[str] = None
    creator_id: Optional[str] = None
    post_rate: Optional[Decimal] = None
    is_showcase: Optional[bool] = None
    content_summary: Optional[List[Dict[str, Any]]] = None
    ad_code: Optional[Any] = None
    actions: Optional[List[Any]] = None
    action_details: Optional[Union[Dict[str, Any], List[Any]]] = None
    logistics_snapshot: Optional[Dict[str, Any]] = None
    type: Optional[str] = None
    type_number: Optional[str] = None
    promotion_name: Optional[str] = None
    promotion_time: Optional[str] = None
    promotion_view_count: Optional[int] = None
    promotion_like_count: Optional[int] = None
    promotion_comment_count: Optional[int] = None
    promotion_order_count: Optional[int] = None
    promotion_order_total_amount: Optional[Decimal] = None
    extracted_time: Optional[str] = None


class SampleIngestionRequest(BaseModel):
    """Request body that collector posts to the inner API."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    source: str = Field(..., description="Source identifier, e.g., portal_tiktok_sample_crawler")
    operator_id: Optional[str] = Field(
        default=None,
        description="Operator/account ID; uses server default if not provided",
    )
    options: Optional[SampleIngestionOptions] = None
    rows: List[SampleRow] = Field(..., min_length=1)


class SampleIngestionResult(BaseModel):
    """Response payload returned to the collector."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    inserted: int = Field(..., description="Total submitted rows (including content rows)")
    products: int = Field(..., description="Unique product count in this submission")
