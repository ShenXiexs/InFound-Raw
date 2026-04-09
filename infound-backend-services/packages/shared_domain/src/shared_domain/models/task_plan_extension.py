from enum import StrEnum


class TaskType(StrEnum):
    """任务类型枚举"""
    OUTREACH = "OUTREACH"
    CREATOR_DETAIL = "CREATOR_DETAIL"
    SAMPLE_MONITOR = "SAMPLE_MONITOR"
    CHAT = "CHAT"
    URGE_CHAT = "URGE_CHAT"


class TaskStatus(StrEnum):
    """任务状态枚举"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
