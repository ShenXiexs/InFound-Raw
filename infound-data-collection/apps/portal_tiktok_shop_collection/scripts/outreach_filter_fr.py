from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from .outreach_filter_base import (
    DEFAULT_OUTREACH_PAGE_READY_TEXT,
    FILTER_TITLE_SELECTOR,
    MODULE_BUTTON_SELECTOR,
    MULTI_SELECT_OPTION_SELECTOR,
    MULTI_SELECT_POPUP_SELECTOR,
    OUTREACH_DSL_REFERENCE,
    POPUP_SCROLL_CONTAINER_SELECTOR,
    OutreachFilterScript,
    build_default_filter_modules,
    build_default_search_binding,
)

if TYPE_CHECKING:
    from ..services.shop_collection_service import ShopAccount, ShopCollectionService

FR_VAT_CHECKBOX_SELECTOR = 'label#isVatProvided_input'


def build_fr_filter_modules() -> list[dict]:
    modules = deepcopy(build_default_filter_modules())

    for module in modules:
        if module["module_key"] == "creatorFilters":
            content_language_filter = None
            for filter_spec in module["filters"]:
                if filter_spec["filter_key"] == "productCategorySelections":
                    filter_spec["filter_title"] = "Product Category"
                    filter_spec["trigger_texts"] = ["Product Category", "Product category"]
                elif filter_spec["filter_key"] == "contentType":
                    content_language_filter = {
                        "filter_key": "contentLanguageSelections",
                        "filter_title": "Content language",
                        "kind": "multi_select",
                        "action_type": "selectDropdownMultiple",
                        "trigger_texts": ["Content language"],
                        "trigger_selector": FILTER_TITLE_SELECTOR,
                        "wait_selector": MULTI_SELECT_POPUP_SELECTOR,
                        "option_selector": MULTI_SELECT_OPTION_SELECTOR,
                        "scroll_container_selector": POPUP_SCROLL_CONTAINER_SELECTOR,
                        "close_mode": "dismiss",
                    }
                elif filter_spec["filter_key"] == "spotlightCreator":
                    filter_spec["filter_title"] = "TikTok creator picks"
                    filter_spec["trigger_texts"] = ["TikTok creator picks", "Rising Star"]

            if content_language_filter:
                insert_at = next(
                    (
                        index + 1
                        for index, filter_spec in enumerate(module["filters"])
                        if filter_spec["filter_key"] == "contentType"
                    ),
                    len(module["filters"]),
                )
                module["filters"].insert(insert_at, content_language_filter)

            module["filters"].append(
                {
                    "filter_key": "vatAuthorised",
                    "filter_title": "VAT authorised",
                    "kind": "checkbox",
                    "action_type": "setCheckbox",
                    "trigger_selector": FR_VAT_CHECKBOX_SELECTOR,
                    "trigger_texts": ["VAT authorised", "VAT legible"],
                    "close_mode": "none",
                }
            )

        elif module["module_key"] == "followerFilters":
            for filter_spec in module["filters"]:
                if filter_spec["filter_key"] == "followerCountRange":
                    filter_spec["filter_title"] = "Follower size"
                    filter_spec["trigger_texts"] = [
                        "Follower size",
                        "Follower count",
                        "Follower c",
                    ]

        elif module["module_key"] == "performanceFilters":
            for filter_spec in module["filters"]:
                if filter_spec["filter_key"] == "itemsSoldSelections":
                    filter_spec["filter_title"] = "Units sold"
                    filter_spec["trigger_texts"] = ["Units sold", "Items sold"]
                elif filter_spec["filter_key"] == "averageViewersPerLiveMin":
                    filter_spec["filter_title"] = "Average viewers per Live"
                    filter_spec["trigger_texts"] = [
                        "Average viewers per Live",
                        "Average viewers per LIVE",
                    ]

    return modules


async def prepare_fr_outreach_page(
    service: "ShopCollectionService",
    account: "ShopAccount",
    timeout_seconds: int,
) -> None:
    del timeout_seconds
    service.logger.info(
        "Skipping FR outreach page pre-processing",
        account_name=account.name,
        current_url=service._page.url if service._page else None,
    )


FR_OUTREACH_FILTER_SCRIPT = OutreachFilterScript(
    region_code="FR",
    page_ready_text=DEFAULT_OUTREACH_PAGE_READY_TEXT,
    dsl_reference=OUTREACH_DSL_REFERENCE,
    module_button_selector=MODULE_BUTTON_SELECTOR,
    filter_title_selector=FILTER_TITLE_SELECTOR,
    filter_modules=build_fr_filter_modules(),
    search_binding=build_default_search_binding(),
    prepare_page_hook=prepare_fr_outreach_page,
)
