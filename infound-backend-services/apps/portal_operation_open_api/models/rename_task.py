from pydantic import BaseModel, Field, field_validator


class RenameTaskRequest(BaseModel):
    task_name: str = Field(..., min_length=1, alias="taskName", description="新的任务名称")

    @field_validator("task_name")
    @classmethod
    def normalize_task_name(cls, value: str) -> str:
        """去除首尾空格"""
        return value.strip()

    class Config:
        populate_by_name = True
