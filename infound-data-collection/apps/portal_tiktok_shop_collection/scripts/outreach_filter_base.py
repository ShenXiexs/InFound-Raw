from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

MODULE_BUTTON_SELECTOR = 'button[data-tid="m4b_button"] span'
FILTER_TITLE_SELECTOR = 'button[data-tid="m4b_button"] .arco-typography'
PRODUCT_CATEGORY_PANEL_SELECTOR = 'ul.arco-cascader-list.arco-cascader-list-multiple'
SINGLE_SELECT_OPTION_SELECTOR = 'li.arco-select-option'
MULTI_SELECT_OPTION_SELECTOR = 'span.arco-select-option.m4b-select-option'
MULTI_SELECT_POPUP_SELECTOR = 'div.arco-select-popup.arco-select-popup-multiple'
FOLLOWER_COUNT_RANGE_SELECTOR = 'div[data-e2e="ec40fffd-2fcf-30d5"]'
FOLLOWER_COUNT_MIN_INPUT_SELECTOR = (
    f'{FOLLOWER_COUNT_RANGE_SELECTOR} input[data-e2e="d9c26458-94d3-e920"]'
)
FOLLOWER_COUNT_MAX_INPUT_SELECTOR = (
    f'{FOLLOWER_COUNT_RANGE_SELECTOR} input[data-e2e="b7512111-8b2f-a07b"]'
)
POPUP_THRESHOLD_INPUT_SELECTOR = 'input[data-tid="m4b_input"][data-e2e="7f6a7b3f-260b-00c0"]'
POPUP_CHECKBOX_LABEL_SELECTOR = 'label[data-tid="m4b_checkbox"]'
POPUP_SCROLL_CONTAINER_SELECTOR = '.arco-select-popup-inner'
DEFAULT_OUTREACH_PAGE_READY_TEXT = 'Find creators'
OUTREACH_DSL_REFERENCE = 'infound-desktop-client-master/apps/frontend.rpa.simulation/src/main/modules/rpa/outreach/support.ts'
SEARCH_INPUT_SELECTOR = 'input[data-tid="m4b_input_search"]'
SORT_BY_TRIGGER_SELECTOR = 'div[role="combobox"][aria-haspopup="listbox"], div.arco-select-view'
SORT_BY_OPTION_SELECTOR = 'li.arco-select-option'

PreparePageHook = Callable[[Any, Any, int], Awaitable[None]]


@dataclass
class OutreachFilterScript:
    region_code: str
    page_ready_text: str
    dsl_reference: str
    module_button_selector: str
    filter_title_selector: str
    filter_modules: List[Dict[str, Any]]
    search_binding: Dict[str, str]
    sort_binding: Optional[Dict[str, Any]] = None
    prepare_page_hook: Optional[PreparePageHook] = None


def build_default_search_binding(
    page_ready_text: str = DEFAULT_OUTREACH_PAGE_READY_TEXT,
) -> Dict[str, str]:
    return {
        "field_key": "searchKeyword",
        "action_type": "fillSelector + clickByText + pressKey",
        "selector": SEARCH_INPUT_SELECTOR,
        "dismiss_text": page_ready_text,
    }


def build_sort_binding(
    *,
    option_map: Dict[int | str, str],
    trigger_selector: str = SORT_BY_TRIGGER_SELECTOR,
    option_selector: str = SORT_BY_OPTION_SELECTOR,
    wait_selector: str = SORT_BY_OPTION_SELECTOR,
    scroll_container_selector: str = POPUP_SCROLL_CONTAINER_SELECTOR,
) -> Dict[str, Any]:
    normalized_option_map: Dict[str, str] = {}
    trigger_texts: List[str] = []
    for key, value in option_map.items():
        numeric_key = str(key).strip()
        label = str(value or "").strip()
        if not numeric_key or not label:
            continue
        normalized_option_map[numeric_key] = label
        if label not in trigger_texts:
            trigger_texts.append(label)

    return {
        "field_key": "filterSortBy",
        "field_title": "Sort by",
        "action_type": "selectDropdownSingle",
        "trigger_selector": trigger_selector,
        "trigger_texts": trigger_texts,
        "wait_selector": wait_selector,
        "option_selector": option_selector,
        "scroll_container_selector": scroll_container_selector,
        "option_map": normalized_option_map,
    }


def build_default_filter_modules() -> List[Dict[str, Any]]:
    return [
        {
            "module_key": "creatorFilters",
            "module_title": "Creators",
            "module_button_fallback_texts": [],
            "filters": [
                {
                    "filter_key": "productCategorySelections",
                    "filter_title": "Product category",
                    "kind": "cascader_multiple",
                    "action_type": "selectCascaderOptionsByValue",
                    "trigger_texts": ["Product category"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "panel_selector": PRODUCT_CATEGORY_PANEL_SELECTOR,
                    "option_selector": f"{PRODUCT_CATEGORY_PANEL_SELECTOR} li",
                    "scroll_container_selector": PRODUCT_CATEGORY_PANEL_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "avgCommissionRate",
                    "filter_title": "Avg. commission rate",
                    "kind": "single_select",
                    "action_type": "selectDropdownSingle",
                    "trigger_texts": ["Avg. commission rate"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": SINGLE_SELECT_OPTION_SELECTOR,
                    "option_selector": SINGLE_SELECT_OPTION_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "contentType",
                    "filter_title": "Content type",
                    "kind": "single_select",
                    "action_type": "selectDropdownSingle",
                    "trigger_texts": ["Content type"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": SINGLE_SELECT_OPTION_SELECTOR,
                    "option_selector": SINGLE_SELECT_OPTION_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "creatorAgency",
                    "filter_title": "Creator agency",
                    "kind": "single_select",
                    "action_type": "selectDropdownSingle",
                    "trigger_texts": ["Creator agency"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": SINGLE_SELECT_OPTION_SELECTOR,
                    "option_selector": SINGLE_SELECT_OPTION_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "spotlightCreator",
                    "filter_title": "Spotlight Creator",
                    "kind": "checkbox",
                    "action_type": "setCheckbox",
                    "trigger_selector": 'label#isRisingStar_input',
                    "close_mode": "none",
                },
                {
                    "filter_key": "fastGrowing",
                    "filter_title": "Fast growing",
                    "kind": "checkbox",
                    "action_type": "setCheckbox",
                    "trigger_selector": 'label#isFastGrowing_input',
                    "close_mode": "none",
                },
                {
                    "filter_key": "notInvitedInPast90Days",
                    "filter_title": "Not invited in past 90 days",
                    "kind": "checkbox",
                    "action_type": "setCheckbox",
                    "trigger_selector": 'label#isInvitedBefore_input',
                    "close_mode": "none",
                },
            ],
        },
        {
            "module_key": "followerFilters",
            "module_title": "Followers",
            "module_button_fallback_texts": ["Follower"],
            "filters": [
                {
                    "filter_key": "followerAgeSelections",
                    "filter_title": "Follower age",
                    "kind": "multi_select",
                    "action_type": "selectDropdownMultiple",
                    "trigger_texts": ["Follower age"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": MULTI_SELECT_POPUP_SELECTOR,
                    "option_selector": MULTI_SELECT_OPTION_SELECTOR,
                    "scroll_container_selector": POPUP_SCROLL_CONTAINER_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "followerGender",
                    "filter_title": "Follower gender",
                    "kind": "single_select",
                    "action_type": "selectDropdownSingle",
                    "trigger_texts": ["Follower gender"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": SINGLE_SELECT_OPTION_SELECTOR,
                    "option_selector": SINGLE_SELECT_OPTION_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "followerCountRange",
                    "filter_title": "Follower count",
                    "kind": "range_input",
                    "action_type": "fillDropdownRange",
                    "trigger_texts": ["Follower count", "Follower c"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": FOLLOWER_COUNT_RANGE_SELECTOR,
                    "min_selector": FOLLOWER_COUNT_MIN_INPUT_SELECTOR,
                    "max_selector": FOLLOWER_COUNT_MAX_INPUT_SELECTOR,
                    "close_mode": "dismiss",
                },
            ],
        },
        {
            "module_key": "performanceFilters",
            "module_title": "Performance",
            "module_button_fallback_texts": [],
            "filters": [
                {
                    "filter_key": "gmvSelections",
                    "filter_title": "GMV",
                    "kind": "multi_select",
                    "action_type": "selectDropdownMultiple",
                    "trigger_texts": ["GMV"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": MULTI_SELECT_POPUP_SELECTOR,
                    "option_selector": MULTI_SELECT_OPTION_SELECTOR,
                    "scroll_container_selector": POPUP_SCROLL_CONTAINER_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "itemsSoldSelections",
                    "filter_title": "Items sold",
                    "kind": "multi_select",
                    "action_type": "selectDropdownMultiple",
                    "trigger_texts": ["Items sold"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": MULTI_SELECT_POPUP_SELECTOR,
                    "option_selector": MULTI_SELECT_OPTION_SELECTOR,
                    "scroll_container_selector": POPUP_SCROLL_CONTAINER_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "averageViewsPerVideoMin",
                    "filter_title": "Average views per video",
                    "kind": "threshold_input",
                    "action_type": "fillDropdownThreshold",
                    "trigger_texts": ["Average views per video"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": POPUP_THRESHOLD_INPUT_SELECTOR,
                    "input_selector": POPUP_THRESHOLD_INPUT_SELECTOR,
                    "checkbox_label_selector": POPUP_CHECKBOX_LABEL_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "averageViewersPerLiveMin",
                    "filter_title": "Average viewers per LIVE",
                    "kind": "threshold_input",
                    "action_type": "fillDropdownThreshold",
                    "trigger_texts": ["Average viewers per LIVE"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": POPUP_THRESHOLD_INPUT_SELECTOR,
                    "input_selector": POPUP_THRESHOLD_INPUT_SELECTOR,
                    "checkbox_label_selector": POPUP_CHECKBOX_LABEL_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "engagementRateMinPercent",
                    "filter_title": "Engagement rate",
                    "kind": "threshold_input",
                    "action_type": "fillDropdownThreshold",
                    "trigger_texts": ["Engagement rate"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": POPUP_THRESHOLD_INPUT_SELECTOR,
                    "input_selector": POPUP_THRESHOLD_INPUT_SELECTOR,
                    "checkbox_label_selector": POPUP_CHECKBOX_LABEL_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "estPostRate",
                    "filter_title": "Est. post rate",
                    "kind": "single_select",
                    "action_type": "selectDropdownSingle",
                    "trigger_texts": ["Est. post rate"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": SINGLE_SELECT_OPTION_SELECTOR,
                    "option_selector": SINGLE_SELECT_OPTION_SELECTOR,
                    "close_mode": "dismiss",
                },
                {
                    "filter_key": "brandCollaborationSelections",
                    "filter_title": "Brand collaborations",
                    "kind": "multi_select",
                    "action_type": "selectDropdownMultiple",
                    "trigger_texts": ["Brand collaborations"],
                    "trigger_selector": FILTER_TITLE_SELECTOR,
                    "wait_selector": MULTI_SELECT_POPUP_SELECTOR,
                    "option_selector": MULTI_SELECT_OPTION_SELECTOR,
                    "scroll_container_selector": POPUP_SCROLL_CONTAINER_SELECTOR,
                    "close_mode": "dismiss",
                },
            ],
        },
    ]
