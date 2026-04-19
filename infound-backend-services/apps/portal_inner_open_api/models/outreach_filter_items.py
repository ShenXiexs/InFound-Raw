from typing import Any, Dict, List, Optional

from pydantic import Field

from shared_application_services import BaseDTO


class OutreachFilterItemsIngestionRequest(BaseDTO):
    region_code: str = Field(..., description="店铺地区编码")
    shop_type: str = Field(..., description="店铺类型")
    creator_filter_items_en: Dict[str, Any] = Field(
        ..., description="英文版 creator_filter_items"
    )
    generated_at: Optional[str] = Field(default=None, description="抓取生成时间")
    capture_source: Optional[str] = Field(default=None, description="抓取来源")
    page_ready_text: Optional[str] = Field(default=None, description="页面就绪文案")
    operator_id: Optional[str] = Field(default=None, description="操作人 ID")


class OutreachFilterItemsIngestionResult(BaseDTO):
    shop_platform_settings_id: str
    region_code: str
    shop_type: str
    stored_locale_keys: List[str]
    untranslated_terms: List[str] = Field(default_factory=list)
    reference_file: str
