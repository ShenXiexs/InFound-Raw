from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from shared_application_services import BaseDTO


class CreatorDetailContextItem(BaseDTO):
    platform: Optional[str] = None
    platform_creator_id: Optional[str] = None
    platform_creator_username: Optional[str] = None
    platform_creator_display_name: Optional[str] = None
    chat_url: Optional[str] = None
    search_keyword: Optional[str] = None
    search_keywords: Optional[str] = None
    brand_name: Optional[str] = None
    categories: Optional[Any] = None
    currency: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    connect: Optional[Any] = None
    reply: Optional[Any] = None
    send: Optional[Any] = None


class CreatorDetailDataItem(BaseDTO):
    creator_id: Optional[str] = None
    region: Optional[str] = None
    target_url: Optional[str] = None
    collected_at_utc: Optional[Any] = None
    creator_name: Optional[str] = None
    creator_rating: Optional[str] = None
    creator_review_count: Optional[str] = None
    creator_followers_count: Optional[str] = None
    creator_mcn: Optional[str] = None
    creator_intro: Optional[str] = None
    gmv: Optional[str] = None
    items_sold: Optional[str] = None
    gpm: Optional[str] = None
    gmv_per_customer: Optional[str] = None
    est_post_rate: Optional[str] = None
    avg_commission_rate: Optional[str] = None
    products: Optional[str] = None
    brand_collaborations: Optional[str] = None
    brands_list: Optional[Any] = None
    product_price: Optional[str] = None
    video_gpm: Optional[str] = None
    videos_count: Optional[str] = None
    avg_video_views: Optional[str] = None
    avg_video_engagement: Optional[str] = None
    avg_video_likes: Optional[str] = None
    avg_video_comments: Optional[str] = None
    avg_video_shares: Optional[str] = None
    live_gpm: Optional[str] = None
    live_streams: Optional[str] = None
    avg_live_views: Optional[str] = None
    avg_live_engagement: Optional[str] = None
    avg_live_likes: Optional[str] = None
    avg_live_comments: Optional[str] = None
    avg_live_shares: Optional[str] = None
    gmv_per_sales_channel: Optional[Any] = None
    gmv_by_product_category: Optional[Any] = None
    follower_gender: Optional[Any] = None
    follower_age: Optional[Any] = None
    videos_list: Optional[Any] = None
    videos_with_product: Optional[Any] = None
    relative_creators: Optional[Any] = None


class CreatorDetailResultIngestionRequest(BaseDTO):
    task_id: str = Field(..., min_length=1)
    shop_id: str = Field(..., min_length=1)
    shop_region_code: Optional[str] = None
    task_name: Optional[str] = None
    platform: Optional[str] = None
    detail: CreatorDetailDataItem
    context: Optional[CreatorDetailContextItem] = None


class CreatorDetailResultIngestionResult(BaseDTO):
    task_id: str
    creator_record_id: str
    crawl_log_id: str
    platform_creator_id: str
