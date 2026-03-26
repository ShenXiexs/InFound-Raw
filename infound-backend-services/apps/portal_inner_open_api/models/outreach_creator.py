from typing import List, Optional

from pydantic import Field

from shared_application_services import BaseDTO


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class OutreachCreatorRow(BaseDTO):
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


class OutreachCreatorIngestionRequest(BaseDTO):
    task_id: str = Field(..., description="建联任务ID")
    platform: str = Field(default="tiktok", description="平台")
    creators: List[OutreachCreatorRow] = Field(..., description="创作者列表")
    operator_id: str = Field(..., description="操作人ID")


class OutreachCreatorIngestionResult(BaseDTO):
    task_id: str
    total_count: int
    success_count: int
    failed_count: int
