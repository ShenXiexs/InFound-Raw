from typing import Any, List
from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class Brand(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    name: str
    only_first: str
    key_word: str


class SearchStrategy(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    search_keywords: str
    product_category: List[str]
    fans_age_range: List[Any]
    fans_gender: str
    min_fans: int
    content_type: List[Any]
    min_GMV: int = Field(alias="minGMV")
    min_sales: List[Any]
    avg_views: int
    min_engagement_rate: int


class EmailContent(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    subject: str
    email_body: str


class OutreachTaskMessage(BaseModel):
    """建联任务消息模型 - 发送到 RabbitMQ"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_id: str
    region: str
    brand: Brand
    search_strategy: SearchStrategy
    email_first: EmailContent
    email_later: EmailContent
    max_creators: int
    target_new_creators: int
    task_name: str
    campaign_id: str
    campaign_name: str
    run_at_time: str
    run_end_time: str
    product_name: str | None = None
    product_id: int | None = None
    action: str = "create"  # create or update
