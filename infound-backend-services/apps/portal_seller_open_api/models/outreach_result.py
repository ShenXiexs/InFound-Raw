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


class OutreachCreatorFilters(BaseDTO):
    product_category_selections: list[str] = Field(default_factory=list)
    avg_commission_rate: Optional[str] = None
    content_type: Optional[str] = None
    creator_agency: Optional[str] = None
    spotlight_creator: Optional[bool] = None
    fast_growing: Optional[bool] = None
    not_invited_in_past_90_days: Optional[bool] = None


class OutreachFollowerFilters(BaseDTO):
    follower_age_selections: list[str] = Field(default_factory=list)
    follower_gender: Optional[str] = None
    follower_count_min: Optional[Any] = None
    follower_count_max: Optional[Any] = None


class OutreachPerformanceFilters(BaseDTO):
    gmv_selections: list[str] = Field(default_factory=list)
    items_sold_selections: list[str] = Field(default_factory=list)
    average_views_per_video_min: Optional[Any] = None
    average_views_per_video_shoppable_videos_only: Optional[bool] = None
    average_viewers_per_live_min: Optional[Any] = None
    average_viewers_per_live_shoppable_live_only: Optional[bool] = None
    engagement_rate_min_percent: Optional[Any] = None
    engagement_rate_shoppable_videos_only: Optional[bool] = None
    est_post_rate: Optional[str] = None
    brand_collaboration_selections: list[str] = Field(default_factory=list)


class OutreachResultIngestionRequest(BaseDTO):
    task_id: str = Field(..., min_length=1)
    shop_id: str = Field(..., min_length=1)
    shop_region_code: Optional[str] = None
    task_name: Optional[str] = None
    task_type: Optional[str] = None
    status: Optional[str] = None
    duplicate_check_type: Optional[Any] = None
    duplicate_check_code: Optional[str] = None
    message_send_strategy: Optional[Any] = None
    message: Optional[str] = None
    search_keyword: Optional[str] = None
    first_message: Optional[str] = None
    second_message: Optional[str] = None
    filter_sort_by: Optional[Any] = None
    plan_execute_time: Optional[Any] = None
    expect_count: Optional[Any] = None
    real_count: Optional[Any] = None
    new_count: Optional[Any] = None
    spend_time: Optional[Any] = None
    started_at: Optional[Any] = None
    finished_at: Optional[Any] = None
    creator_filters: Optional[OutreachCreatorFilters] = None
    follower_filters: Optional[OutreachFollowerFilters] = None
    performance_filters: Optional[OutreachPerformanceFilters] = None
    creators: list[OutreachCreatorResultItem] = Field(default_factory=list)


class OutreachResultIngestionResult(BaseDTO):
    task_id: str
    inserted_task_logs: int
    updated_creator_counts: int
    real_count: int
    new_count: int
