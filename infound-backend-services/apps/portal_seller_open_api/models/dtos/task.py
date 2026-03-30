from pydantic import Field, AliasChoices

from shared_application_services.dtos.base import BaseDTO
from shared_domain.models.task_plan_extension import TaskStatus


class TaskReportRequest(BaseDTO):
    status: TaskStatus = Field(
        validation_alias=AliasChoices("status"),
        serialization_alias="status",
        description="任务状态"
    )
    error: str = Field(
        validation_alias=AliasChoices("error"),
        serialization_alias="error",
        description="错误信息",
        min_length=0,
        max_length=1024,
    )
