from pydantic import BaseModel, ConfigDict
from typing import Optional, Any


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class SampleDetailResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    id: str
    status: str
    content_summary: Optional[Any] = None
    ad_code: Optional[Any] = None
    platform_product_id: str
    product_name: str
    thumbnail: str
    shooting_guide: Optional[str] = None
    platform_creator_username: str
    platform_creator_display_name: str
    email: Optional[str] = None
    whatsapp: Optional[str] = None
