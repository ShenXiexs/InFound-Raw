from typing import Optional, Any

from shared_application_services import BaseDTO


class SampleDetailResponse(BaseDTO):
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
