from __future__ import annotations

from typing import TYPE_CHECKING

from .outreach_filter_base import (
    DEFAULT_OUTREACH_PAGE_READY_TEXT,
    FILTER_TITLE_SELECTOR,
    MODULE_BUTTON_SELECTOR,
    OUTREACH_DSL_REFERENCE,
    OutreachFilterScript,
    build_default_filter_modules,
    build_default_search_binding,
)

if TYPE_CHECKING:
    from ..services.shop_collection_service import ShopAccount, ShopCollectionService


async def prepare_vn_outreach_page(
    service: "ShopCollectionService",
    account: "ShopAccount",
    timeout_seconds: int,
) -> None:
    del timeout_seconds
    service.logger.info(
        "Skipping VN outreach page language switch",
        account_name=account.name,
        current_url=service._page.url if service._page else None,
    )


VN_OUTREACH_FILTER_SCRIPT = OutreachFilterScript(
    region_code="VN",
    page_ready_text=DEFAULT_OUTREACH_PAGE_READY_TEXT,
    dsl_reference=OUTREACH_DSL_REFERENCE,
    module_button_selector=MODULE_BUTTON_SELECTOR,
    filter_title_selector=FILTER_TITLE_SELECTOR,
    filter_modules=build_default_filter_modules(),
    search_binding=build_default_search_binding(),
    prepare_page_hook=prepare_vn_outreach_page,
)
