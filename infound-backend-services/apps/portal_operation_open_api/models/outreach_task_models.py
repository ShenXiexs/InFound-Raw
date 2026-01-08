from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


# ======================
# 通用子结构
# ======================

class Progress(BaseModel):
    current: int = Field(..., description="当前已建联人数")
    target: int = Field(..., description="目标建联人数")


class SearchStrategy(BaseModel):
    searchKeywords: Optional[str] = None
    productCategories: Optional[List[str]] = None
    fansAgeRange: Optional[List[str]] = None
    fansGender: Optional[Dict[str, Any]] = None
    contentTypes: Optional[List[str]] = None
    gmvRange: Optional[List[Any]] = None
    salesRange: Optional[List[Any]] = None
    minFans: Optional[int] = None
    minAvgViews: Optional[int] = None
    minEngagementRate: Optional[int] = None


class MessageContent(BaseModel):
    first: Optional[str] = None
    second: Optional[str] = None


class PlanInfo(BaseModel):
    startTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    targetCreators: Optional[int] = None
    maxCreators: Optional[int] = None


class RuntimeInfo(BaseModel):
    spendTime: Optional[int] = None
    realStartAt: Optional[datetime] = None
    realEndAt: Optional[datetime] = None
    currentCreators: Optional[int] = None


# ======================
# 列表
# ======================

class OutreachTaskItem(BaseModel):
    taskId: str
    taskName: str
    status: Optional[str]
    platform: Optional[str]

    region: Optional[str]
    planStartTime: Optional[datetime]
    planEndTime: Optional[datetime]
    spendTime: Optional[int]

    progress: Progress
    createdAt: datetime


class OutreachTaskListData(BaseModel):
    total: int
    list: List[OutreachTaskItem]


# ======================
# 详情
# ======================

class OutreachTaskDetailData(BaseModel):
    taskId: str
    taskName: str
    status: Optional[str]
    platform: Optional[str]

    region: Optional[str]
    campaignId: Optional[str]
    campaignName: Optional[str]
    brand: Optional[str]
    productId: Optional[str]
    productName: Optional[str]

    messageSendStrategy: Optional[int]

    searchStrategy: SearchStrategy
    messages: MessageContent
    plan: PlanInfo
    runtime: RuntimeInfo

    createdAt: datetime
