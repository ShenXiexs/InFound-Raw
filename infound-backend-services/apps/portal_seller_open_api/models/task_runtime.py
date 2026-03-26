from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SellerRpaTaskType(StrEnum):
    OUTREACH = "OUTREACH"
    CREATOR_DETAIL = "CREATOR_DETAIL"
    CHAT = "CHAT"
    SAMPLE_MONITOR = "SAMPLE_MONITOR"


class SellerRpaTaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SellerRpaTaskClaimResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    task_type: str
    task_status: str
    task_data: Any
    created_at: datetime
    updated_at: datetime
    scheduled_time: datetime
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    heartbeat_at: Optional[datetime] = None


class SellerRpaTaskHeartbeatResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str
    task_status: str
    heartbeat_at: datetime


class SellerRpaTaskReportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_status: SellerRpaTaskStatus = Field(...)
    error: Optional[str] = None


class SellerRpaTaskReportResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str
    task_status: str
    end_time: datetime
    error: Optional[str] = None


class SellerRpaTaskClaimRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_type: SellerRpaTaskType = Field(...)
    task_id: Optional[str] = None
