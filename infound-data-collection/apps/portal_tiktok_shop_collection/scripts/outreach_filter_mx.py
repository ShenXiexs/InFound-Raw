from .outreach_filter_base import (
    DEFAULT_OUTREACH_PAGE_READY_TEXT,
    FILTER_TITLE_SELECTOR,
    MODULE_BUTTON_SELECTOR,
    OUTREACH_DSL_REFERENCE,
    OutreachFilterScript,
    build_default_filter_modules,
    build_default_search_binding,
)

MX_OUTREACH_FILTER_SCRIPT = OutreachFilterScript(
    region_code="MX",
    page_ready_text=DEFAULT_OUTREACH_PAGE_READY_TEXT,
    dsl_reference=OUTREACH_DSL_REFERENCE,
    module_button_selector=MODULE_BUTTON_SELECTOR,
    filter_title_selector=FILTER_TITLE_SELECTOR,
    filter_modules=build_default_filter_modules(),
    search_binding=build_default_search_binding(),
)
