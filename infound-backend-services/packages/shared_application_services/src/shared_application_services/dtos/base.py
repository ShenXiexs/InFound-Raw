import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Optional, List

from pydantic import BaseModel, ConfigDict, BeforeValidator
from pydantic.alias_generators import to_camel


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _parse_percent(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    try:
        if text.endswith("%"):
            number = Decimal(text.replace("%", "").strip()) / Decimal("100")
        else:
            number = Decimal(text)
        return str(number.normalize())
    except Exception:
        return None


def _parse_period_list(value: Any) -> Optional[List[str]]:
    """将输入统一转换为清洗后的字符串列表"""
    if value is None:
        return None
    # 如果已经是列表，清洗每个元素
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    # 如果是单值（如字符串），清洗并包装成列表
    text = str(value).strip() if value is not None else ""
    return [text] if text else None


def _parse_flexible_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value

    # 1. 基础清洗 (复用之前的 _clean_text 逻辑)
    text = str(value).strip() if value is not None else ""
    if not text:
        return None

    # 2. 尝试多种格式解析
    formats = ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    # 3. 如果都不匹配，可以让 Pydantic 尝试其默认解析逻辑，或者直接返回 None
    # return None
    return value  # 返回原值交给 Pydantic 默认解析器（比如处理 ISO 格式）


def _parse_flexible_decimal(value: Any) -> Optional[Decimal]:
    # 1. 基础转换逻辑 (复用你原有的代码)
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    # 2. 清洗字符串：去空格、去逗号（处理 1,234.56）
    text = str(value).strip().replace(",", "")
    if not text:
        return None

    # 3. 正则提取数字（处理 "$12.3" -> "12.3"）
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None

    try:
        return Decimal(match.group(0))
    except (InvalidOperation, ValueError):
        return None


# 定义重用拦截器
CleanStr = Annotated[str, BeforeValidator(_clean_text)]
FlexibleInt = Annotated[int, BeforeValidator(_to_int)]
PercentStr = Annotated[str, BeforeValidator(_parse_percent)]
PeriodList = Annotated[Optional[List[str]], BeforeValidator(_parse_period_list)]
FlexibleDatetime = Annotated[
    Optional[datetime], BeforeValidator(_parse_flexible_datetime)
]
FlexibleDecimal = Annotated[Optional[Decimal], BeforeValidator(_parse_flexible_decimal)]


class BaseDTO(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    def to_orm(self, model_class):
        """通用转换逻辑"""
        # 只提取 DTO 和数据库 Model 共同拥有的字段
        data = self.model_dump()
        column_names = [c.name for c in model_class.__table__.columns]
        payload = {k: v for k, v in data.items() if k in column_names}
        return model_class(**payload)
