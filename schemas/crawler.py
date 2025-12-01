"""
爬虫相关数据模型
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _AllowExtraModel(BaseModel):
    """允许额外字段的基类，保留来自前端的扩展配置。"""

    model_config = ConfigDict(extra="allow")


class EmailTemplate(_AllowExtraModel):
    """邮件模版配置"""

    subject: str = Field(..., description="邮件主题")
    email_body: str = Field(..., description="邮件正文")


class BrandInfo(_AllowExtraModel):
    """品牌信息配置"""

    name: str = Field(..., description="品牌名称")
    only_first: int = Field(0, description="消息发送策略：0=全部，1=仅新达人，2=仅历史未回复达人")
    key_word: Optional[str] = Field(default="", description="品牌关键词")


SALES_CODE_DEFINITIONS = [
    {"code": "0-10", "lower": 0, "upper": 10, "label": "0-10"},
    {"code": "10-100", "lower": 10, "upper": 100, "label": "10-100"},
    {"code": "100-1k", "lower": 100, "upper": 1000, "label": "100-1K"},
    {"code": "1k+", "lower": 1000, "upper": None, "label": "1K+"},
]

DEFAULT_MIN_SALES_THRESHOLD = 10


class SearchStrategy(_AllowExtraModel):
    """搜索策略配置"""

    search_keywords: Optional[str] = ""
    product_category: Optional[str] = ""
    fans_age_range: List[str] = Field(default_factory=list)
    fans_gender: Optional[str] = ""
    min_fans: Optional[int] = None
    content_type: List[str] = Field(default_factory=list)
    gmv: List[str] = Field(default_factory=list, description="GMV 区间编码列表，例如 ['0-100', '100-1k']")
    sales: List[str] = Field(default_factory=list, description="销量区间编码列表，例如 ['0-10', '10-100']")
    min_GMV: Optional[int] = None  # 兼容旧版本
    max_GMV: Optional[int] = None  # 兼容旧版本
    legacy_min_sales: List[str] = Field(
        default_factory=list,
        alias="min_sales",
        exclude=True,
        description="兼容旧字段，解析后会自动转为 sales",
    )
    avg_views: Optional[int] = None
    min_engagement_rate: float = 0.0

    @field_validator("fans_age_range", "content_type", mode="before")
    @classmethod
    def _ensure_list_of_str(cls, value):
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if str(item).strip()]
        return [str(value)]

    @field_validator("sales", mode="before")
    @classmethod
    def _ensure_list_of_sales(cls, value):
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value)]

    @field_validator("gmv", mode="before")
    @classmethod
    def _ensure_list_of_gmv(cls, value):
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value)]

    @field_validator("legacy_min_sales", mode="before")
    @classmethod
    def _ensure_list_of_legacy_sales(cls, value):
        if value in (None, "", []):
            return []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(value)]

    @field_validator("min_engagement_rate", mode="before")
    @classmethod
    def _normalize_min_engagement_rate(cls, value):
        if value in (None, "", [], {}):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return 0.0
            cleaned = cleaned.replace("%", "").strip()
            if not cleaned:
                return 0.0
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0

    @model_validator(mode="after")
    def _apply_legacy_min_sales(self):
        sales_provided = "sales" in self.model_fields_set
        legacy_provided = "legacy_min_sales" in self.model_fields_set

        normalized_sales = self._normalize_sales_input(self.sales)
        if normalized_sales:
            self.sales = normalized_sales
            return self
        if sales_provided:
            self.sales = []
            return self

        legacy_sales = self._normalize_sales_input(self.legacy_min_sales)
        if legacy_sales:
            self.sales = legacy_sales
            return self
        if legacy_provided:
            self.sales = []
            return self

        self.sales = self._codes_from_threshold(DEFAULT_MIN_SALES_THRESHOLD)
        return self

    @staticmethod
    def _normalize_sales_code(code: Any) -> Optional[str]:
        if code in (None, "", []):
            return None
        s = str(code).strip().lower()
        s = (
            s.replace(" ", "")
            .replace("–", "-")
            .replace("—", "-")
            .replace("to", "-")
            .replace("_", "-")
            .replace("plus", "+")
        )
        s = s.replace(",", "")
        if s in {"0-10", "0_10"}:
            return "0-10"
        if s in {"10-100", "10_100"}:
            return "10-100"
        if s in {"100-1k", "100-1000", "100-1k+", "100_1k"}:
            return "100-1k"
        if s in {"1k+", "1000+", "1k", "1000"}:
            return "1k+"
        return None

    @staticmethod
    def _extract_numeric_threshold(value: Any) -> Optional[int]:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            match = re.search(r"(\d+)", value)
            if match:
                return int(match.group(1))
        return None

    @classmethod
    def _codes_from_threshold(cls, threshold: int) -> List[str]:
        if threshold <= 0:
            return [entry["code"] for entry in SALES_CODE_DEFINITIONS]
        if threshold <= 10:
            return [entry["code"] for entry in SALES_CODE_DEFINITIONS[1:]]
        if threshold <= 100:
            return [entry["code"] for entry in SALES_CODE_DEFINITIONS[2:]]
        if threshold <= 1000:
            return [SALES_CODE_DEFINITIONS[3]["code"]]
        return []

    @classmethod
    def _normalize_sales_input(cls, raw: Any) -> List[str]:
        if raw in (None, "", []):
            return []
        if isinstance(raw, (list, tuple)):
            items = list(raw)
        else:
            items = [raw]

        codes: List[str] = []
        numeric_thresholds: List[int] = []

        for item in items:
            if item in (None, "", []):
                continue
            normalized_code = cls._normalize_sales_code(item)
            if normalized_code:
                if normalized_code not in codes:
                    codes.append(normalized_code)
                continue
            threshold = cls._extract_numeric_threshold(item)
            if threshold is not None:
                numeric_thresholds.append(threshold)

        if not codes and numeric_thresholds:
            threshold = min(numeric_thresholds)
            for code in cls._codes_from_threshold(threshold):
                if code not in codes:
                    codes.append(code)

        return codes

    @field_validator("product_category", mode="before")
    @classmethod
    def _normalize_product_category(cls, value):
        if value in (None, ""):
            return ""
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item).strip() for item in value if str(item).strip())
        return str(value).strip()


class CrawlerTaskPayload(_AllowExtraModel):
    """前端提交的完整任务配置"""

    task_name: Optional[str] = Field(default=None, description="任务名称（可选）")
    region: Optional[str] = Field(default="", description="区域代码，如 MX / FR")
    product_name: Optional[str] = Field(default=None, description="主推产品名称（可选）")
    product_id: Optional[str] = Field(default=None, description="主推产品ID（可选）")
    campaign_id: Optional[str] = Field(default=None, description="营销活动ID")
    campaign_name: Optional[str] = Field(default=None, description="营销活动名称")
    run_end_time: Optional[datetime] = Field(default=None, description="任务强制结束时间（北京时间）")
    brand: BrandInfo
    search_strategy: SearchStrategy
    email_first: EmailTemplate
    email_later: Optional[EmailTemplate] = None

    @model_validator(mode="after")
    def _ensure_email_later(self):
        def _template_blank(template: Optional[EmailTemplate]) -> bool:
            if template is None:
                return True
            subject = (template.subject or "").strip()
            body = (template.email_body or "").strip()
            return not subject and not body

        only_first = None
        if self.brand and self.brand.only_first is not None:
            try:
                only_first = int(self.brand.only_first)
            except (TypeError, ValueError):
                only_first = self.brand.only_first

        requires_follow_up = only_first in (0, 2)
        if requires_follow_up and _template_blank(self.email_later):
            self.email_later = self.email_first
        elif self.email_later is None:
            self.email_later = self.email_first

        return self


class CrawlerTaskCreateRequest(CrawlerTaskPayload):
    """创建任务请求体"""

    max_creators: int = Field(500, description="单次任务最大达人数量")
    target_new_creators: int = Field(50, description="期望新增达人数量")
    note: Optional[str] = Field(default=None, description="任务备注")
    task_id: Optional[str] = Field(default=None, description="自定义任务ID（可选）")
    run_at_time: Optional[datetime] = Field(default=None, description="计划执行时间（北京时间）")

    @field_validator("max_creators", "target_new_creators")
    @classmethod
    def _validate_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("数值必须大于0")
        return value

    @field_validator("task_id", mode="before")
    @classmethod
    def _clean_task_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("run_at_time", mode="before")
    @classmethod
    def _parse_run_at_time(cls, value):
        if value in (None, "", []):
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            raise ValueError("run_at_time 需为日期时间字符串")
        value = str(value).strip()
        # 支持 ISO 字符串或 "YYYY-MM-DD HH:MM" 格式
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
            except ValueError as exc:
                raise ValueError("run_at_time 格式应为 ISO8601 或 'YYYY-MM-DD HH:MM'") from exc
        if dt.tzinfo is None:
            from zoneinfo import ZoneInfo

            dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return dt

    @field_validator("run_end_time", mode="before")
    @classmethod
    def _parse_run_end_time(cls, value):
        if value in (None, "", []):
            return None
        if isinstance(value, datetime):
            return value
        value = str(value).strip()
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
            except ValueError as exc:
                raise ValueError("run_end_time 格式应为 ISO8601 或 'YYYY-MM-DD HH:MM'") from exc
        if dt.tzinfo is None:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return dt


class CrawlerTaskUpdateRequest(_AllowExtraModel):
    """更新任务请求体（仅在任务未执行时可修改）"""

    task_name: Optional[str] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    brand: Optional[BrandInfo] = None
    search_strategy: Optional[SearchStrategy] = None
    email_first: Optional[EmailTemplate] = None
    email_later: Optional[EmailTemplate] = None
    max_creators: Optional[int] = Field(default=None, description="新的最大达人数量")
    target_new_creators: Optional[int] = Field(default=None, description="新的目标新增达人数量")
    note: Optional[str] = None
    run_at_time: Optional[datetime] = Field(default=None, description="新的计划执行时间（北京时间）")
    run_end_time: Optional[datetime] = Field(default=None, description="新的任务终止时间（北京时间）")
    task_id: Optional[str] = Field(default=None, description="必须与原任务ID一致（若传入）")

    @field_validator("max_creators", "target_new_creators", mode="before")
    @classmethod
    def _validate_positive_optional(cls, value):
        if value is None:
            return value
        ivalue = int(value)
        if ivalue <= 0:
            raise ValueError("数值必须大于0")
        return ivalue

    @field_validator("task_id", mode="before")
    @classmethod
    def _clean_task_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("run_at_time", mode="before")
    @classmethod
    def _parse_run_at_time(cls, value):
        if value is None:
            return None
        if value == "":
            return None
        if isinstance(value, datetime):
            return value
        value = str(value).strip()
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
            except ValueError as exc:
                raise ValueError("run_at_time 格式应为 ISO8601 或 'YYYY-MM-DD HH:MM'") from exc
        if dt.tzinfo is None:
            from zoneinfo import ZoneInfo

            dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return dt

    @field_validator("run_end_time", mode="before")
    @classmethod
    def _parse_run_end_time(cls, value):
        if value is None:
            return None
        if value == "":
            return None
        if isinstance(value, datetime):
            return value
        value = str(value).strip()
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M")
            except ValueError as exc:
                raise ValueError("run_end_time 格式应为 ISO8601 或 'YYYY-MM-DD HH:MM'") from exc
        if dt.tzinfo is None:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return dt


class CrawlerTaskRenameRequest(BaseModel):
    task_name: str = Field(..., min_length=1, description="新的任务名称")

    @field_validator("task_name")
    @classmethod
    def _normalize_task_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("任务名称不能为空")
        return name


class CrawlerTaskStatus(BaseModel):
    """任务状态"""

    task_id: str
    task_type: Literal["Connect", "Card"] = Field(
        default="Connect", description="任务类型：Connect 或 Card"
    )
    status: Literal[
        "pending",
        "to-be-run",
        "running",
        "to-be-cancel",
        "completed",
        "failed",
        "cancelled",
    ]
    message: Optional[str] = None
    submitted_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    user: Optional[str] = None
    task_name: Optional[str] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    region: Optional[str] = None
    brand_name: Optional[str] = None
    account_email: Optional[str] = None
    new_creators: Optional[int] = None
    total_creators: Optional[int] = None
    task_dir: Optional[str] = None
    log_path: Optional[str] = None
    product_name: Optional[str] = None
    product_id: Optional[str] = None
    connect_creator: Optional[str] = None
    run_time: Optional[str] = Field(
        default=None,
        description="任务已运行时长（格式：xxhxxminxxs）",
    )
    payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="任务原始配置（包含 brand/search/email 等全部字段）",
    )
    output_files: List[str] = Field(default_factory=list)
    max_creators: Optional[int] = None
    target_new_creators: Optional[int] = None
    run_at_time: Optional[datetime] = None
    run_end_time: Optional[datetime] = None


class CrawlerTaskListResponse(BaseModel):
    """任务列表响应"""

    tasks: List[CrawlerTaskStatus]
    total: int


class CrawlerSummaryResponse(BaseModel):
    """爬虫任务整体状态汇总"""

    total: int
    pending: int
    to_be_run: int = Field(0, description="任务正在准备启动")
    running: int
    to_be_cancel: int = Field(0, description="任务正在取消中")
    completed: int
    failed: int
    cancelled: int
    in_queue: int = Field(0, description="排队中的任务数量")
