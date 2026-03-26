from __future__ import annotations

from typing import Any, List, Optional

from pydantic import Field

from shared_application_services import BaseDTO


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class CampaignIngestionOptions(BaseDTO):
    campaign_id: Optional[str] = None
    campaign_ids: Optional[List[str]] = None
    account_name: Optional[str] = None
    region: Optional[str] = None
    scan_all_pages: Optional[bool] = None
    max_pages: Optional[int] = None
    export_excel: Optional[bool] = None


class CampaignRow(BaseDTO):
    platform_campaign_id: str = Field(..., min_length=1)
    platform_shop_id: Optional[str] = None
    platform_campaign_name: Optional[str] = None
    region: Optional[str] = None
    platform: Optional[str] = None
    status: Optional[str] = None
    registration_period: Optional[Any] = None
    campaign_period: Optional[Any] = None
    pending_product_count: Optional[Any] = None
    approved_product_count: Optional[Any] = None
    date_registered: Optional[str] = None
    commission_rate: Optional[str] = None
    platform_shop_name: Optional[str] = None
    platform_shop_phone: Optional[str] = None


class ProductRow(BaseDTO):
    platform_product_id: str = Field(..., min_length=1)
    platform_campaign_id: str = Field(..., min_length=1)
    platform_shop_id: Optional[str] = None
    region: Optional[str] = None
    platform: Optional[str] = None
    platform_shop_name: Optional[str] = None
    platform_shop_phone: Optional[str] = None
    thumbnail: Optional[str] = None
    product_name: Optional[str] = None
    product_rating: Optional[Any] = None
    reviews_count: Optional[Any] = None
    product_sku: Optional[str] = None
    stock: Optional[Any] = None
    available_sample_count: Optional[Any] = None
    item_sold: Optional[Any] = None
    sale_price_min: Optional[Any] = None
    sale_price_max: Optional[Any] = None


class CampaignIngestionRequest(BaseDTO):
    source: str = Field(
        ..., description="数据来源标识，例如 portal_tiktok_campaign_crawler"
    )
    operator_id: Optional[str] = Field(
        default=None,
        description="操作人/账号 ID，若未提供则使用服务端默认值",
    )
    options: Optional[CampaignIngestionOptions] = None
    rows: List[CampaignRow] = Field(..., min_length=1)


class ProductIngestionRequest(BaseDTO):
    source: str = Field(
        ..., description="数据来源标识，例如 portal_tiktok_campaign_crawler"
    )
    operator_id: Optional[str] = Field(
        default=None,
        description="操作人/账号 ID，若未提供则使用服务端默认值",
    )
    options: Optional[CampaignIngestionOptions] = None
    rows: List[ProductRow] = Field(..., min_length=1)


class CampaignIngestionResult(BaseDTO):
    inserted: int = Field(..., description="本次提交的总行数")
    campaigns: int = Field(..., description="涉及的唯一活动数量")


class ProductIngestionResult(BaseDTO):
    inserted: int = Field(..., description="本次提交的总行数")
    products: int = Field(..., description="涉及的唯一商品数量")
