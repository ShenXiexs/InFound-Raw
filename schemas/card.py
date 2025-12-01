from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class CardTaskStatus(BaseModel):
    task_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    task_type: Literal["Card"] = "Card"
    message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    creator_file: str
    product_file: str
    output_json: Optional[str] = None
    output_files: List[str] = Field(default_factory=list)
    task_dir: Optional[str] = None
    record_count: int = Field(0, description="生成的商品卡记录数量")
    generate_only: bool = Field(False, description="是否仅生成 JSON 而未执行发送")
    headless: bool = True
    verify_delivery: bool = True
    manual_login_timeout: int = 600
    created_by: str
    region: str = Field("MX", description="发送任务使用的账号区域")
    account_name: Optional[str] = Field(
        default=None, description="发送任务使用的账号名称（config/accounts.json 中的 name）"
    )


class CardTaskListResponse(BaseModel):
    tasks: List[CardTaskStatus]
    total: int


class CardTaskCreateResponse(BaseModel):
    task_id: str
    status: CardTaskStatus
