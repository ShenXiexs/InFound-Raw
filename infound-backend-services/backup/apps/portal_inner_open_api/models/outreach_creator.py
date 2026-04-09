from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class OutreachCreatorRow(BaseModel):
    """单个建联创作者数据"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    platform_creator_id: str
    platform_creator_display_name: str
    platform_creator_username: str
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    introduction: Optional[str] = None
    region: Optional[str] = None
    fans_count: Optional[int] = None
    avg_views: Optional[int] = None
    engagement_rate: Optional[float] = None


class OutreachCreatorIngestionRequest(BaseModel):
    """建联创作者数据上报请求"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_id: str = Field(..., description="建联任务ID")
    platform: str = Field(default="tiktok", description="平台")
    creators: List[OutreachCreatorRow] = Field(..., description="创作者列表")
    operator_id: str = Field(..., description="操作人ID")


class OutreachCreatorIngestionResult(BaseModel):
    """建联创作者数据上报结果"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_id: str
    total_count: int
    success_count: int
    failed_count: int
