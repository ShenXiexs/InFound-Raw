from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class Brand(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    name: str
    only_first: int
    key_word: str

    @field_validator("only_first", mode="before")
    @classmethod
    def _normalize_only_first(cls, value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return 1
        if text in {"false", "0", "no", "n", ""}:
            return 0
        try:
            return int(float(text))
        except ValueError:
            return 0


class SearchStrategy(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    search_keywords: str
    product_category: List[str]
    fans_age_range: List[Any]
    fans_gender: str
    min_fans: int
    content_type: List[Any]
    gmv: Optional[List[Any]] = None
    sales: Optional[List[Any]] = None
    min_GMV: Optional[int] = None
    min_sales: Optional[List[Any]] = None
    avg_views: int
    min_engagement_rate: int

    @model_validator(mode="before")
    @classmethod
    def _normalize_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        alias_map = {
            "searchKeywords": "search_keywords",
            "productCategories": "product_category",
            "productCategory": "product_category",
            "fansAgeRange": "fans_age_range",
            "fansGender": "fans_gender",
            "minFans": "min_fans",
            "contentTypes": "content_type",
            "contentType": "content_type",
            "gmvRange": "gmv",
            "salesRange": "sales",
            "minAvgViews": "avg_views",
            "avgViews": "avg_views",
            "minEngagementRate": "min_engagement_rate",
            "minGMV": "min_GMV",
            "minGmv": "min_GMV",
            "minSales": "min_sales",
        }
        for src, dest in alias_map.items():
            if src in data and dest not in data:
                data[dest] = data[src]
        return data

    @model_validator(mode="after")
    def _ensure_ranges(self) -> "SearchStrategy":
        if self.gmv in (None, []) and self.min_GMV is None:
            raise ValueError("gmvRange or min_GMV is required")
        if self.sales in (None, []) and not self.min_sales:
            raise ValueError("salesRange or min_sales is required")
        return self


class EmailContent(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    subject: str
    email_body: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_body(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "body" in data and "email_body" not in data:
            data["email_body"] = data["body"]
        return data


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_name: str
    region: str
    campaign_id: str
    campaign_name: str
    product_id: int
    product_name: str
    brand: Brand
    search_strategy: SearchStrategy
    email_first: EmailContent
    email_later: EmailContent
    max_creators: int
    target_new_creators: int
    run_at_time: str
    run_end_time: str
    product_list: Optional[Any] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_product_list(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "productList" in data and "product_list" not in data:
            data["product_list"] = data["productList"]
        return data


class UpdateTaskRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_name: str
    region: str
    campaign_id: str
    campaign_name: str
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    brand: Brand
    search_strategy: SearchStrategy
    email_first: EmailContent
    email_later: EmailContent
    max_creators: int
    target_new_creators: int
    run_at_time: str
    run_end_time: str
    product_list: Optional[Any] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_product_list(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "productList" in data and "product_list" not in data:
            data["product_list"] = data["productList"]
        return data


class UpdateTaskNameRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    task_name: str
