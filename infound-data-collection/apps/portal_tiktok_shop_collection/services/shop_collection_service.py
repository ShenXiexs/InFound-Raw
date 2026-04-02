from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from common.core.config import get_settings
from common.core.exceptions import PlaywrightError
from common.core.logger import get_logger
from ..scripts import get_outreach_filter_script, has_outreach_filter_script
from ..scripts.outreach_filter_base import OutreachFilterScript
from ..scripts.outreach_filter_snapshot_export import (
    build_creator_filter_items_payload,
    derive_creator_filter_items_output_path,
)

logger = get_logger()

OUTREACH_PAGE_URL = 'https://affiliate.tiktok.com/connection/creator?shop_region={region}'
OUTREACH_DATA_DIR = 'apps/portal_tiktok_shop_collection/data/outreach-filter-snapshots'


@dataclass
class ShopAccount:
    name: str
    region: str
    shop_type: str
    login_email: str
    login_password: Optional[str]
    entry_url: str
    home_url: str
    enabled: bool = True
    notes: str = ""


class ShopCollectionService:
    """Manual-login seller bootstrap plus seller-region outreach filter snapshot capture."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.headless = bool(getattr(self.settings, "PLAYWRIGHT_HEADLESS", False))
        self.manual_login_default = bool(
            getattr(self.settings, "SHOP_COLLECTION_MANUAL_LOGIN", True)
        )
        self.manual_login_timeout_seconds = int(
            getattr(
                self.settings,
                "SHOP_COLLECTION_MANUAL_LOGIN_TIMEOUT_SECONDS",
                900,
            )
            or 900
        )
        self.entry_page_timeout_seconds = int(
            getattr(
                self.settings,
                "SHOP_COLLECTION_ENTRY_PAGE_TIMEOUT_SECONDS",
                120,
            )
            or 120
        )
        self.account_config_path = getattr(
            self.settings,
            "SHOP_COLLECTION_ACCOUNT_CONFIG_PATH",
            "configs/accounts.json",
        )
        self.default_capture_enabled = bool(
            getattr(self.settings, "SHOP_COLLECTION_CAPTURE_OUTREACH_FILTERS", True)
        )
        self.default_capture_region = str(
            getattr(self.settings, "SHOP_COLLECTION_CAPTURE_REGION", "MX") or "MX"
        ).upper()
        self.default_capture_timeout_seconds = int(
            getattr(
                self.settings,
                "SHOP_COLLECTION_CAPTURE_TIMEOUT_SECONDS",
                60,
            )
            or 60
        )
        self.default_capture_output_dir = getattr(
            self.settings,
            "SHOP_COLLECTION_CAPTURE_OUTPUT_DIR",
            OUTREACH_DATA_DIR,
        )
        self.accounts = self._load_accounts()

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self.current_url: str = ""
        self._active_outreach_filter_script: Optional[OutreachFilterScript] = None

    async def run_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        account = self.resolve_account(
            account_name=payload.get("accountName"),
            region=payload.get("region"),
            shop_type=payload.get("shopType"),
        )
        entry_url = self._normalize_url(
            payload.get("entryUrl") or account.entry_url or account.home_url
        )
        home_url = self._normalize_url(
            payload.get("homeUrl") or account.home_url
        )

        if not entry_url:
            raise ValueError(
                f"No entry URL configured for account '{account.name}'. "
                "Provide SHOP_COLLECTION_BOOTSTRAP_ENTRY_URL or update the account config."
            )

        await self.initialize()
        await self._open_page(entry_url)

        login_confirmed = True
        wait_for_manual_login = bool(
            payload.get("waitForManualLogin", self.manual_login_default)
        )
        if wait_for_manual_login:
            login_confirmed = await self._wait_for_manual_login(
                entry_url=entry_url,
                home_url=home_url,
                timeout_seconds=int(
                    payload.get(
                        "manualLoginTimeoutSeconds",
                        self.manual_login_timeout_seconds,
                    )
                    or self.manual_login_timeout_seconds
                ),
            )

        if home_url and self._page and self._should_jump_to_home(self._page.url, home_url):
            await self._open_page(home_url)

        filter_snapshot_path = ""
        creator_filter_items_path = ""
        capture_filters = bool(
            payload.get(
                "captureOutreachFilters",
                self.default_capture_enabled,
            )
        )
        capture_region = str(
            payload.get("captureRegion") or self.default_capture_region
        ).upper()
        capture_output_dir = str(
            payload.get("captureOutputDir") or self.default_capture_output_dir
        ).strip()

        if capture_filters and login_confirmed:
            filter_snapshot_path = await self.capture_outreach_filter_snapshot(
                account=account,
                region=capture_region,
                output_dir=capture_output_dir,
                timeout_seconds=int(
                    payload.get(
                        "captureTimeoutSeconds",
                        self.default_capture_timeout_seconds,
                    )
                    or self.default_capture_timeout_seconds
                ),
            )
            creator_filter_items_path = str(
                derive_creator_filter_items_output_path(Path(filter_snapshot_path))
            )
        elif capture_filters:
            self.logger.warning(
                "Skip filter snapshot because manual login was not confirmed",
                account_name=account.name,
                current_url=self.current_url,
            )

        self.current_url = self._page.url if self._page else ""
        self.logger.info(
            "Shop collection page prepared",
            account_name=account.name,
            region=account.region,
            shop_type=account.shop_type,
            current_url=self.current_url,
            filter_snapshot_path=filter_snapshot_path or None,
            creator_filter_items_path=creator_filter_items_path or None,
        )
        return {
            "accountName": account.name,
            "region": account.region,
            "shopType": account.shop_type,
            "currentUrl": self.current_url,
            "filterSnapshotPath": filter_snapshot_path,
            "creatorFilterItemsPath": creator_filter_items_path,
        }

    async def initialize(self) -> None:
        if self._page:
            return

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()
        self.logger.info("Playwright session initialized", headless=self.headless)

    async def close(self) -> None:
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def resolve_account(
        self,
        *,
        account_name: Optional[str],
        region: Optional[str],
        shop_type: Optional[str],
    ) -> ShopAccount:
        enabled_accounts = [account for account in self.accounts if account.enabled]

        if account_name:
            for account in enabled_accounts:
                if account.name == str(account_name).strip():
                    return account
            raise ValueError(f"Shop account '{account_name}' was not found.")

        region_value = str(region or "").strip().upper()
        shop_type_value = str(shop_type or "").strip().lower()

        for account in enabled_accounts:
            if region_value and account.region.upper() != region_value:
                continue
            if shop_type_value and account.shop_type.lower() != shop_type_value:
                continue
            return account

        if enabled_accounts:
            return enabled_accounts[0]
        raise ValueError("No enabled shop accounts are configured.")

    async def capture_outreach_filter_snapshot(
        self,
        *,
        account: ShopAccount,
        region: str,
        output_dir: str,
        timeout_seconds: int,
    ) -> str:
        if not self._page:
            raise PlaywrightError("Playwright page has not been initialized")

        outreach_script = self._resolve_outreach_filter_script(region)
        self._active_outreach_filter_script = outreach_script
        target_url = self._normalize_url(
            OUTREACH_PAGE_URL.format(region=quote(region, safe=""))
        )
        try:
            self.logger.info(
                "Navigating to outreach filter page",
                account_name=account.name,
                region=region,
                target_url=target_url,
                script_region=outreach_script.region_code,
            )
            await self._page.goto(target_url, wait_until="domcontentloaded")
            await self._page.wait_for_load_state("domcontentloaded")
            await self._prepare_outreach_page(
                account=account,
                timeout_seconds=timeout_seconds,
            )
            await self._wait_for_page_texts(
                [outreach_script.page_ready_text],
                timeout_seconds=timeout_seconds,
            )
            await asyncio.sleep(2)
            self.current_url = self._page.url
            self.logger.info(
                "Starting outreach filter snapshot capture",
                account_name=account.name,
                region=region,
                current_url=self.current_url,
                module_count=len(outreach_script.filter_modules),
                script_region=outreach_script.region_code,
            )

            modules: List[Dict[str, Any]] = []
            sort_binding_snapshot: Dict[str, Any] | None = None
            if outreach_script.sort_binding:
                sort_binding_snapshot = await self._capture_sort_binding_snapshot(
                    outreach_script.sort_binding
                )
            for module_spec in outreach_script.filter_modules:
                module_snapshot = await self._capture_module_snapshot(module_spec)
                modules.append(module_snapshot)

            payload = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "capture_type": "affiliate_outreach_filters",
                "region": region,
                "account_name": account.name,
                "shop_type": account.shop_type,
                "target_url": target_url,
                "current_url": self._page.url,
                "source": {
                    "service_name": "portal_tiktok_shop_collection",
                    "dsl_reference": outreach_script.dsl_reference,
                    "page_ready_text": outreach_script.page_ready_text,
                    "module_button_selector": outreach_script.module_button_selector,
                    "filter_title_selector": outreach_script.filter_title_selector,
                    "script_region": outreach_script.region_code,
                },
                "modules": modules,
                "sort_binding": sort_binding_snapshot,
                "search_binding": dict(outreach_script.search_binding),
            }

            output_path = self._build_output_path(output_dir, account.name, region)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            creator_filter_items_payload = build_creator_filter_items_payload(payload)
            creator_filter_items_output_path = derive_creator_filter_items_output_path(output_path)
            creator_filter_items_output_path.write_text(
                json.dumps(creator_filter_items_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.logger.info(
                "Outreach filter snapshot saved",
                output_path=str(output_path),
                module_count=len(modules),
            )
            self.logger.info(
                "Creator filter items snapshot saved",
                output_path=str(creator_filter_items_output_path),
                module_count=len(creator_filter_items_payload.get("modules", [])),
            )
            self.logger.info(
                "Outreach search binding prepared",
                field_key=payload["search_binding"]["field_key"],
                selector=payload["search_binding"]["selector"],
                action_type=payload["search_binding"]["action_type"],
            )
            return str(output_path)
        finally:
            self._active_outreach_filter_script = None

    def _resolve_outreach_filter_script(self, region: str) -> OutreachFilterScript:
        region_code = str(region or "").upper()
        script = get_outreach_filter_script(region_code)
        if region_code and not has_outreach_filter_script(region_code):
            self.logger.warning(
                "Using fallback outreach filter script",
                requested_region=region_code,
                script_region=script.region_code,
            )
        else:
            self.logger.info(
                "Selected outreach filter script",
                requested_region=region_code or script.region_code,
                script_region=script.region_code,
            )
        return script

    def _require_active_outreach_filter_script(self) -> OutreachFilterScript:
        if not self._active_outreach_filter_script:
            raise PlaywrightError("No active outreach filter script is selected")
        return self._active_outreach_filter_script

    async def _prepare_outreach_page(
        self,
        *,
        account: ShopAccount,
        timeout_seconds: int,
    ) -> None:
        outreach_script = self._require_active_outreach_filter_script()
        if not outreach_script.prepare_page_hook:
            return
        await outreach_script.prepare_page_hook(self, account, timeout_seconds)

    async def _page_has_all_texts(self, texts: List[str]) -> bool:
        if not self._page:
            raise PlaywrightError("Playwright page has not been initialized")

        return bool(
            await self._page.evaluate(
                """
                (texts) => {
                  const bodyText = document.body?.innerText || ''
                  return texts.every((text) => bodyText.includes(text))
                }
                """,
                texts,
            )
        )

    async def _wait_for_page_texts(self, texts: List[str], *, timeout_seconds: int) -> None:
        if not self._page:
            raise PlaywrightError("Playwright page has not been initialized")

        await self._page.wait_for_function(
            """
            (texts) => {
              const bodyText = document.body?.innerText || ''
              return texts.every((text) => bodyText.includes(text))
            }
            """,
            arg=texts,
            timeout=max(timeout_seconds, 1) * 1000,
        )

    async def _click_first_matching_text_element(
        self,
        *,
        selectors: List[str],
        texts: List[str],
        exact: bool,
        wait_ms: int,
        prefer_last: bool = False,
    ) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for _ in range(5):
            for selector in selectors:
                try:
                    return await self._click_text_element(
                        selector=selector,
                        texts=texts,
                        exact=exact,
                        wait_ms=wait_ms,
                        prefer_last=prefer_last,
                    )
                except Exception as exc:
                    last_error = exc
            await asyncio.sleep(0.4)

        if last_error:
            raise last_error
        raise PlaywrightError(
            f"Failed to find visible element by texts={texts!r} selectors={selectors!r}"
        )

    async def _click_first_visible_selector(
        self,
        *,
        selectors: List[str],
        wait_ms: int,
        prefer_last: bool = False,
    ) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for _ in range(5):
            for selector in selectors:
                try:
                    return await self._click_visible_selector(
                        selector=selector,
                        wait_ms=wait_ms,
                        prefer_last=prefer_last,
                    )
                except Exception as exc:
                    last_error = exc
            await asyncio.sleep(0.4)

        if last_error:
            raise last_error
        raise PlaywrightError(
            f"Failed to find visible element by selectors={selectors!r}"
        )

    async def _capture_module_snapshot(self, module_spec: Dict[str, Any]) -> Dict[str, Any]:
        outreach_script = self._require_active_outreach_filter_script()
        self.logger.info(
            "Capturing outreach module",
            module_key=module_spec["module_key"],
            module_title=module_spec["module_title"],
            filter_count=len(module_spec["filters"]),
        )
        module_button = await self._click_text_element(
            selector=outreach_script.module_button_selector,
            texts=[module_spec["module_title"], *module_spec.get("module_button_fallback_texts", [])],
            exact=True,
            wait_ms=350,
        )
        observed_titles = await self._collect_visible_texts(outreach_script.filter_title_selector)
        self.logger.info(
            "Outreach module titles discovered",
            module_key=module_spec["module_key"],
            module_title=module_spec["module_title"],
            observed_filter_titles=observed_titles,
        )
        filters: List[Dict[str, Any]] = []
        for filter_spec in module_spec["filters"]:
            try:
                filter_snapshot = await self._capture_filter_snapshot(module_spec, filter_spec)
            except Exception as exc:
                self.logger.error(
                    "Outreach filter capture failed",
                    module_key=module_spec["module_key"],
                    module_title=module_spec["module_title"],
                    filter_key=filter_spec["filter_key"],
                    filter_title=filter_spec["filter_title"],
                    filter_kind=filter_spec["kind"],
                    error=str(exc),
                )
                filter_snapshot = {
                    "filter_key": filter_spec["filter_key"],
                    "filter_title": filter_spec["filter_title"],
                    "status": "error",
                    "error": str(exc),
                    "dsl_binding": self._build_dsl_binding(module_spec, filter_spec),
                }
            filters.append(filter_snapshot)

        ok_count = sum(1 for item in filters if item.get("status") == "ok")
        error_count = sum(1 for item in filters if item.get("status") != "ok")
        self.logger.info(
            "Outreach module capture completed",
            module_key=module_spec["module_key"],
            module_title=module_spec["module_title"],
            ok_count=ok_count,
            error_count=error_count,
        )

        return {
            "module_key": module_spec["module_key"],
            "module_title": module_spec["module_title"],
            "module_button": module_button,
            "observed_filter_titles": observed_titles,
            "filters": filters,
        }

    async def _capture_sort_binding_snapshot(
        self,
        sort_binding_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.logger.info(
            "Capturing outreach sort binding",
            field_key=sort_binding_spec.get("field_key"),
            field_title=sort_binding_spec.get("field_title"),
        )
        trigger_metadata = await self._click_text_element(
            selector=sort_binding_spec["trigger_selector"],
            texts=sort_binding_spec.get("trigger_texts", ["Relevancy"]),
            exact=False,
            wait_ms=300,
            prefer_last=True,
        )
        snapshot = await self._extract_popup_snapshot(sort_binding_spec)
        await self._dismiss_filter_overlay({"close_mode": "dismiss"})
        result = {
            "field_key": sort_binding_spec.get("field_key", "filterSortBy"),
            "field_title": sort_binding_spec.get("field_title", "Sort by"),
            "status": "ok",
            "trigger": trigger_metadata,
            "dsl_binding": self._build_sort_dsl_binding(sort_binding_spec),
            "snapshot": snapshot,
        }
        self.logger.info(
            "Outreach sort binding captured",
            field_key=result["field_key"],
            field_title=result["field_title"],
            **self._build_filter_log_fields(snapshot),
        )
        return result

    async def _capture_filter_snapshot(
        self,
        module_spec: Dict[str, Any],
        filter_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        filter_kind = filter_spec["kind"]
        trigger_metadata: Dict[str, Any] | None = None
        self.logger.info(
            "Capturing outreach filter",
            module_key=module_spec["module_key"],
            module_title=module_spec["module_title"],
            filter_key=filter_spec["filter_key"],
            filter_title=filter_spec["filter_title"],
            filter_kind=filter_kind,
        )

        if filter_kind in {"single_select", "multi_select", "cascader_multiple", "range_input", "threshold_input"}:
            trigger_metadata = await self._click_text_element(
                selector=filter_spec["trigger_selector"],
                texts=filter_spec.get("trigger_texts", [filter_spec["filter_title"]]),
                exact=False,
                wait_ms=300,
            )
            snapshot = await self._extract_popup_snapshot(filter_spec)
            await self._dismiss_filter_overlay(filter_spec)
        elif filter_kind == "checkbox":
            snapshot = await self._extract_checkbox_snapshot(filter_spec)
        else:
            raise ValueError(f"Unsupported filter kind: {filter_kind}")

        result = {
            "filter_key": filter_spec["filter_key"],
            "filter_title": filter_spec["filter_title"],
            "filter_kind": filter_kind,
            "status": "ok",
            "trigger": trigger_metadata,
            "dsl_binding": self._build_dsl_binding(module_spec, filter_spec),
            "snapshot": snapshot,
        }
        self.logger.info(
            "Outreach filter captured",
            module_key=module_spec["module_key"],
            module_title=module_spec["module_title"],
            filter_key=filter_spec["filter_key"],
            filter_title=filter_spec["filter_title"],
            filter_kind=filter_kind,
            **self._build_filter_log_fields(snapshot),
        )
        return result

    async def _extract_popup_snapshot(self, filter_spec: Dict[str, Any]) -> Dict[str, Any]:
        if not self._page:
            raise PlaywrightError("Playwright page has not been initialized")

        return await self._page.evaluate(
            """
            async (spec) => {
              const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms))
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim()
              const matchKey = (value) => normalize(value).toLowerCase()
              const isVisible = (node) => {
                if (!(node instanceof Element)) return false
                const style = window.getComputedStyle(node)
                const rect = node.getBoundingClientRect()
                return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0
              }
              const domPath = (node) => {
                if (!(node instanceof Element)) return ''
                const segments = []
                let current = node
                while (current && current.nodeType === Node.ELEMENT_NODE && segments.length < 6) {
                  let segment = current.tagName.toLowerCase()
                  if (current.id) segment += `#${current.id}`
                  const classNames = Array.from(current.classList).slice(0, 2)
                  if (classNames.length) segment += `.${classNames.join('.')}`
                  segments.unshift(segment)
                  current = current.parentElement
                }
                return segments.join(' > ')
              }
              const collectMatches = (root, selector) => {
                if (!selector || !(root instanceof Element || root instanceof Document)) return []
                const nodes = []
                if (root instanceof Element && root.matches(selector) && isVisible(root)) {
                  nodes.push(root)
                }
                for (const node of Array.from(root.querySelectorAll(selector)).filter(isVisible)) {
                  nodes.push(node)
                }
                return nodes
              }
              const resolvePopupRoot = (node) => {
                if (!(node instanceof Element)) return null
                return (
                  node.closest('.arco-select-popup') ||
                  node.closest('.arco-cascader-popup') ||
                  node.closest('.arco-trigger-popup') ||
                  node.closest('#filter-container') ||
                  node.closest('[role="dialog"]') ||
                  node
                )
              }
              const candidateRootSelectors = [
                spec.panel_selector,
                spec.wait_selector,
                spec.input_selector,
                spec.min_selector,
                spec.max_selector,
                spec.checkbox_label_selector,
                spec.option_selector
              ].filter(Boolean)
              const candidateRoots = []
              for (const selector of candidateRootSelectors) {
                for (const node of collectMatches(document, selector)) {
                  const root = resolvePopupRoot(node)
                  if (root && isVisible(root) && !candidateRoots.includes(root)) {
                    candidateRoots.push(root)
                  }
                }
              }
              const popupIndex = (node) => {
                if (!(node instanceof Element)) return -1
                const matched = (node.id || '').match(/(?:select|cascader|trigger)-popup-(\\d+)/)
                if (!matched) return -1
                return Number(matched[1] || -1)
              }
              const scoreRoot = (root) => {
                if (!(root instanceof Element)) {
                  return { popupIndex: -1, optionCount: -1, inputCount: -1 }
                }
                const optionCount = spec.option_selector
                  ? collectMatches(root, spec.option_selector).length
                  : 0
                const inputSelector = [spec.input_selector, spec.min_selector, spec.max_selector]
                  .filter(Boolean)
                  .join(',')
                const inputCount = inputSelector
                  ? collectMatches(root, inputSelector).length
                  : 0
                return {
                  popupIndex: popupIndex(root),
                  optionCount,
                  inputCount
                }
              }
              candidateRoots.sort((left, right) => {
                const leftScore = scoreRoot(left)
                const rightScore = scoreRoot(right)
                if (leftScore.popupIndex !== rightScore.popupIndex) {
                  return leftScore.popupIndex - rightScore.popupIndex
                }
                if (leftScore.optionCount !== rightScore.optionCount) {
                  return leftScore.optionCount - rightScore.optionCount
                }
                if (leftScore.inputCount !== rightScore.inputCount) {
                  return leftScore.inputCount - rightScore.inputCount
                }
                return 0
              })
              const activeRoot = candidateRoots.at(-1) || null
              const queryVisible = (selector) => {
                if (!selector) return []
                const scopedNodes = activeRoot ? collectMatches(activeRoot, selector) : []
                if (scopedNodes.length > 0) return scopedNodes
                return collectMatches(document, selector)
              }
              const collectOptions = (selector) => {
                if (!selector) return []
                const nodes = queryVisible(selector)
                const seen = new Set()
                const items = []
                for (const node of nodes) {
                  const label = normalize(node.textContent)
                  const value =
                    normalize(node.getAttribute('value')) ||
                    normalize(node.getAttribute('data-value')) ||
                    normalize(node.getAttribute('data-key')) ||
                    normalize(node.querySelector('input')?.getAttribute('value')) ||
                    ''
                  const key = `${label}::${value}`
                  if (!label && !value) continue
                  if (seen.has(key)) continue
                  seen.add(key)
                  items.push({
                    label,
                    value,
                    tag_name: node.tagName.toLowerCase(),
                    class_name: node.className || '',
                    dom_path: domPath(node),
                    input_value: normalize(node.querySelector('input')?.getAttribute('value') || ''),
                    input_checked: Boolean(node.querySelector('input')?.checked)
                  })
                }
                return items
              }
              const resolveContainer = () => {
                const candidates = [
                  spec.scroll_container_selector,
                  spec.panel_selector,
                  spec.wait_selector,
                  spec.option_selector,
                  spec.input_selector
                ].filter(Boolean)
                for (const selector of candidates) {
                  const node = queryVisible(selector).at(-1)
                  if (node) return node
                }
                return activeRoot
              }
              const scrollContainer = resolveContainer()
              const seen = new Map()
              const merge = (items) => {
                for (const item of items) {
                  const key = `${item.label}::${item.value}::${item.dom_path}`
                  if (!seen.has(key)) seen.set(key, item)
                }
              }
              const initialItems = spec.option_selector ? collectOptions(spec.option_selector) : []
              merge(initialItems)

              if (
                scrollContainer instanceof HTMLElement &&
                spec.scroll_container_selector &&
                spec.option_selector
              ) {
                let previousTop = -1
                for (let attempt = 0; attempt < 20; attempt += 1) {
                  scrollContainer.scrollTop = Math.min(
                    scrollContainer.scrollTop + 360,
                    scrollContainer.scrollHeight
                  )
                  await sleep(120)
                  merge(collectOptions(spec.option_selector))
                  if (scrollContainer.scrollTop === previousTop) break
                  previousTop = scrollContainer.scrollTop
                }
                scrollContainer.scrollTop = 0
              }

              const inputSelector = [spec.input_selector, spec.min_selector, spec.max_selector]
                .filter(Boolean)
                .join(',')
              const inputNodes = inputSelector ? queryVisible(inputSelector) : []
              const checkboxNodes = spec.checkbox_label_selector ? queryVisible(spec.checkbox_label_selector) : []
              const buttonTexts = (() => {
                const scope = activeRoot || document
                const nodes = collectMatches(scope, 'button, [role="button"], label')
                const seenTexts = new Set()
                const texts = []
                for (const node of nodes) {
                  const text = normalize(node.textContent)
                  if (!text || text.length > 80) continue
                  const token = matchKey(text)
                  if (!token || seenTexts.has(token)) continue
                  seenTexts.add(token)
                  texts.push(text)
                }
                return texts
              })()

              return {
                container_selector: spec.panel_selector || spec.wait_selector || spec.scroll_container_selector || '',
                active_root_dom_path: domPath(activeRoot),
                option_selector: spec.option_selector || '',
                option_count: seen.size,
                options: Array.from(seen.values()),
                inputs: inputNodes.map((node) => ({
                  value: normalize(node.value || ''),
                  placeholder: normalize(node.getAttribute('placeholder') || ''),
                  dom_path: domPath(node),
                  input_type: normalize(node.getAttribute('type') || '')
                })),
                checkbox_labels: checkboxNodes.map((node) => ({
                  label: normalize(node.textContent),
                  dom_path: domPath(node)
                })),
                button_texts: buttonTexts,
                body_text_preview: normalize(document.body?.innerText || '').slice(0, 500)
              }
            }
            """,
            filter_spec,
        )

    async def _extract_checkbox_snapshot(self, filter_spec: Dict[str, Any]) -> Dict[str, Any]:
        if not self._page:
            raise PlaywrightError("Playwright page has not been initialized")

        return await self._page.evaluate(
            """
            (spec) => {
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim()
              const isVisible = (node) => {
                if (!(node instanceof Element)) return false
                const style = window.getComputedStyle(node)
                const rect = node.getBoundingClientRect()
                return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0
              }
              const domPath = (node) => {
                if (!(node instanceof Element)) return ''
                const segments = []
                let current = node
                while (current && current.nodeType === Node.ELEMENT_NODE && segments.length < 6) {
                  let segment = current.tagName.toLowerCase()
                  if (current.id) segment += `#${current.id}`
                  const classNames = Array.from(current.classList).slice(0, 2)
                  if (classNames.length) segment += `.${classNames.join('.')}`
                  segments.unshift(segment)
                  current = current.parentElement
                }
                return segments.join(' > ')
              }
              const triggerTexts = Array.isArray(spec.trigger_texts)
                ? spec.trigger_texts.map(matchKey).filter(Boolean)
                : []
              const node = Array.from(document.querySelectorAll(spec.trigger_selector))
                .filter(isVisible)
                .find((candidate) => {
                  if (!triggerTexts.length) return true
                  const text = matchKey(candidate.textContent)
                  return triggerTexts.some((token) => text.includes(token))
                })
              if (!(node instanceof HTMLElement)) {
                return {
                  found: false,
                  selector: spec.trigger_selector
                }
              }
              const input = node.querySelector('input')
              return {
                found: true,
                selector: spec.trigger_selector,
                label: normalize(node.textContent),
                checked: Boolean(input?.checked),
                dom_path: domPath(node)
              }
            }
            """,
            filter_spec,
        )

    async def _dismiss_filter_overlay(self, filter_spec: Dict[str, Any]) -> None:
        if not self._page or filter_spec.get("close_mode") != "dismiss":
            return

        outreach_script = self._require_active_outreach_filter_script()
        try:
            await self._click_text_element(
                selector='button span, h1, h2, h3, p, span, div',
                texts=[outreach_script.page_ready_text],
                exact=True,
                wait_ms=150,
            )
            return
        except Exception:
            pass

        try:
            await self._page.keyboard.press("Escape")
            await asyncio.sleep(0.15)
        except Exception:
            self.logger.info(
                "Failed to dismiss overlay via keyboard",
                filter_key=filter_spec.get("filter_key"),
            )

    async def _collect_visible_texts(self, selector: str) -> List[str]:
        if not self._page:
            raise PlaywrightError("Playwright page has not been initialized")

        return await self._page.evaluate(
            """
            (selector) => {
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim()
              const isVisible = (node) => {
                if (!(node instanceof Element)) return false
                const style = window.getComputedStyle(node)
                const rect = node.getBoundingClientRect()
                return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0
              }
              const seen = new Set()
              const items = []
              for (const node of Array.from(document.querySelectorAll(selector)).filter(isVisible)) {
                const text = normalize(node.textContent)
                if (!text || seen.has(text)) continue
                seen.add(text)
                items.push(text)
              }
              return items
            }
            """,
            selector,
        )

    async def _click_text_element(
        self,
        *,
        selector: str,
        texts: List[str],
        exact: bool,
        wait_ms: int,
        prefer_last: bool = False,
    ) -> Dict[str, Any]:
        if not self._page:
            raise PlaywrightError("Playwright page has not been initialized")

        result = await self._page.evaluate(
            """
            async (payload) => {
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim()
              const matchKey = (value) => normalize(value).toLowerCase()
              const isVisible = (node) => {
                if (!(node instanceof Element)) return false
                const style = window.getComputedStyle(node)
                const rect = node.getBoundingClientRect()
                return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0
              }
              const domPath = (node) => {
                if (!(node instanceof Element)) return ''
                const segments = []
                let current = node
                while (current && current.nodeType === Node.ELEMENT_NODE && segments.length < 6) {
                  let segment = current.tagName.toLowerCase()
                  if (current.id) segment += `#${current.id}`
                  const classNames = Array.from(current.classList).slice(0, 2)
                  if (classNames.length) segment += `.${classNames.join('.')}`
                  segments.unshift(segment)
                  current = current.parentElement
                }
                return segments.join(' > ')
              }
              const candidates = Array.from(document.querySelectorAll(payload.selector)).filter(isVisible)
              const normalizedTexts = payload.texts.map((item) => matchKey(item))
              const orderedCandidates = payload.prefer_last ? candidates.slice().reverse() : candidates
              const matched = orderedCandidates.find((node) => {
                const text = matchKey(node.textContent)
                if (!text) return false
                if (payload.exact) {
                  return normalizedTexts.includes(text)
                }
                return normalizedTexts.some((token) => text.includes(token))
              })
              if (!(matched instanceof HTMLElement)) {
                return null
              }
              matched.scrollIntoView({ block: 'center', inline: 'center' })
              matched.click()
              return {
                text: normalize(matched.textContent),
                selector: payload.selector,
                dom_path: domPath(matched),
                class_name: matched.className || '',
                aria_expanded: matched.getAttribute('aria-expanded') || '',
                data_tid: matched.getAttribute('data-tid') || ''
              }
            }
            """,
            {
                "selector": selector,
                "texts": texts,
                "exact": exact,
                "prefer_last": prefer_last,
            },
        )

        if not result:
            raise PlaywrightError(
                f"Failed to find visible element by texts={texts!r} selector={selector!r}"
            )
        await asyncio.sleep(wait_ms / 1000)
        return result

    async def _click_visible_selector(
        self,
        *,
        selector: str,
        wait_ms: int,
        prefer_last: bool = False,
    ) -> Dict[str, Any]:
        if not self._page:
            raise PlaywrightError("Playwright page has not been initialized")

        result = await self._page.evaluate(
            """
            async (payload) => {
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim()
              const isVisible = (node) => {
                if (!(node instanceof Element)) return false
                const style = window.getComputedStyle(node)
                const rect = node.getBoundingClientRect()
                return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0
              }
              const domPath = (node) => {
                if (!(node instanceof Element)) return ''
                const segments = []
                let current = node
                while (current && current.nodeType === Node.ELEMENT_NODE && segments.length < 6) {
                  let segment = current.tagName.toLowerCase()
                  if (current.id) segment += `#${current.id}`
                  const classNames = Array.from(current.classList).slice(0, 2)
                  if (classNames.length) segment += `.${classNames.join('.')}`
                  segments.unshift(segment)
                  current = current.parentElement
                }
                return segments.join(' > ')
              }
              const candidates = Array.from(document.querySelectorAll(payload.selector)).filter(isVisible)
              const orderedCandidates = payload.prefer_last ? candidates.slice().reverse() : candidates
              const matched = orderedCandidates[0]
              if (!(matched instanceof HTMLElement)) {
                return null
              }
              matched.scrollIntoView({ block: 'center', inline: 'center' })
              matched.click()
              return {
                text: normalize(matched.textContent),
                selector: payload.selector,
                dom_path: domPath(matched),
                class_name: matched.className || '',
                aria_expanded: matched.getAttribute('aria-expanded') || '',
                data_tid: matched.getAttribute('data-tid') || ''
              }
            }
            """,
            {
                "selector": selector,
                "prefer_last": prefer_last,
            },
        )

        if not result:
            raise PlaywrightError(
                f"Failed to find visible element by selector={selector!r}"
            )
        await asyncio.sleep(wait_ms / 1000)
        return result

    def _build_dsl_binding(
        self,
        module_spec: Dict[str, Any],
        filter_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        binding = {
            "module_key": module_spec["module_key"],
            "module_title": module_spec["module_title"],
            "filter_key": filter_spec["filter_key"],
            "filter_title": filter_spec["filter_title"],
            "action_type": filter_spec["action_type"],
            "trigger_selector": filter_spec.get("trigger_selector", ""),
            "trigger_texts": filter_spec.get("trigger_texts", [filter_spec["filter_title"]]),
        }
        for key in (
            "panel_selector",
            "wait_selector",
            "option_selector",
            "scroll_container_selector",
            "min_selector",
            "max_selector",
            "input_selector",
            "checkbox_label_selector",
        ):
            if filter_spec.get(key):
                binding[key] = filter_spec[key]
        return binding

    def _build_sort_dsl_binding(self, sort_binding_spec: Dict[str, Any]) -> Dict[str, Any]:
        binding = {
            "field_key": sort_binding_spec.get("field_key", "filterSortBy"),
            "field_title": sort_binding_spec.get("field_title", "Sort by"),
            "action_type": sort_binding_spec.get("action_type", "selectDropdownSingle"),
            "trigger_selector": sort_binding_spec.get("trigger_selector", ""),
            "trigger_texts": sort_binding_spec.get("trigger_texts", []),
        }
        for key in (
            "wait_selector",
            "option_selector",
            "scroll_container_selector",
            "option_map",
        ):
            if sort_binding_spec.get(key):
                binding[key] = sort_binding_spec[key]
        return binding

    def _build_filter_log_fields(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        options = snapshot.get("options") or []
        inputs = snapshot.get("inputs") or []
        checkbox_labels = snapshot.get("checkbox_labels") or []
        button_texts = snapshot.get("button_texts") or []
        option_preview = [
            str(item.get("label") or item.get("value") or "").strip()
            for item in options
            if str(item.get("label") or item.get("value") or "").strip()
        ][:8]
        input_preview = [
            str(item.get("value") or item.get("placeholder") or "").strip()
            for item in inputs
        ][:4]
        checkbox_preview = [
            str(item.get("label") or "").strip()
            for item in checkbox_labels
            if str(item.get("label") or "").strip()
        ][:6]

        fields: Dict[str, Any] = {
            "option_count": len(options),
            "option_preview": option_preview,
            "input_count": len(inputs),
            "input_preview": input_preview,
            "checkbox_count": len(checkbox_labels),
            "checkbox_preview": checkbox_preview,
            "button_count": len(button_texts),
            "button_preview": [str(item).strip() for item in button_texts if str(item).strip()][:6],
            "active_root_dom_path": snapshot.get("active_root_dom_path"),
        }
        if "found" in snapshot:
            fields["found"] = bool(snapshot.get("found"))
        if "checked" in snapshot:
            fields["checked"] = bool(snapshot.get("checked"))
        if snapshot.get("label"):
            fields["label"] = snapshot.get("label")
        return fields

    async def _open_page(self, url: str) -> None:
        if not self._page:
            raise PlaywrightError("Playwright page has not been initialized")

        timeout_ms = max(self.entry_page_timeout_seconds, 1) * 1000
        self.logger.info(
            "Opening seller page",
            url=url,
            timeout_seconds=self.entry_page_timeout_seconds,
        )
        await self._page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        try:
            await self._page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            self.logger.info("Page reached DOM ready before network idle", url=self._page.url)
        self.current_url = self._page.url

    async def _wait_for_manual_login(
        self,
        *,
        entry_url: str,
        home_url: Optional[str],
        timeout_seconds: int,
    ) -> bool:
        if not self._page:
            raise PlaywrightError("Playwright page has not been initialized")

        self.logger.info(
            "Waiting for manual login",
            account_entry_url=entry_url,
            home_url=home_url,
            timeout_seconds=timeout_seconds,
        )
        deadline = asyncio.get_running_loop().time() + max(timeout_seconds, 0)
        while asyncio.get_running_loop().time() < deadline:
            current_url = self._page.url
            self.current_url = current_url
            if self._looks_logged_in(
                current_url=current_url,
                entry_url=entry_url,
                home_url=home_url,
            ):
                self.logger.info("Manual login detected", current_url=current_url)
                return True
            await asyncio.sleep(1)

        self.logger.warning(
            "Manual login wait timed out; keeping browser open",
            current_url=self._page.url,
        )
        return False

    def _load_accounts(self) -> List[ShopAccount]:
        path = self._resolve_path(self.account_config_path)
        with path.open("r", encoding="utf-8") as file_obj:
            payload = json.load(file_obj) or {}

        accounts: List[ShopAccount] = []
        for raw in payload.get("accounts", []):
            accounts.append(
                ShopAccount(
                    name=str(raw.get("name") or "").strip(),
                    region=str(raw.get("region") or "").strip().upper(),
                    shop_type=str(raw.get("shop_type") or raw.get("shopType") or "local").strip(),
                    login_email=str(raw.get("login_email") or "").strip(),
                    login_password=raw.get("login_password"),
                    entry_url=str(raw.get("entry_url") or raw.get("entryUrl") or "").strip(),
                    home_url=str(raw.get("home_url") or raw.get("homeUrl") or "").strip(),
                    enabled=bool(raw.get("enabled", True)),
                    notes=str(raw.get("notes") or "").strip(),
                )
            )
        return accounts

    def _build_output_path(self, output_dir: str, account_name: str, region: str) -> Path:
        directory = self._resolve_path(output_dir, allow_missing=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = self._slugify(account_name)
        return directory / f"outreach_filters_{region.lower()}_{slug}_{timestamp}.json"

    def _resolve_path(self, configured_path: str, *, allow_missing: bool = False) -> Path:
        candidate = Path(configured_path)
        app_dir = Path(__file__).resolve().parents[1]
        repo_root = Path(__file__).resolve().parents[3]

        if candidate.is_absolute():
            return candidate

        options = [
            app_dir / candidate,
            repo_root / candidate,
            Path.cwd() / candidate,
        ]
        for option in options:
            if option.exists():
                return option

        if allow_missing:
            return repo_root / candidate
        return options[0]

    @staticmethod
    def _normalize_url(raw_url: Optional[str]) -> str:
        text = str(raw_url or "").strip()
        if not text:
            return ""
        if "://" not in text:
            text = f"https://{text.lstrip('/')}"
        return text

    @staticmethod
    def _looks_logged_in(
        *,
        current_url: str,
        entry_url: str,
        home_url: Optional[str],
    ) -> bool:
        if home_url and ShopCollectionService._same_page(current_url, home_url):
            return True
        if ShopCollectionService._looks_like_auth_page(current_url):
            return False
        if not ShopCollectionService._same_page(current_url, entry_url):
            return True
        return False

    @staticmethod
    def _should_jump_to_home(current_url: str, home_url: str) -> bool:
        return not ShopCollectionService._same_page(current_url, home_url)

    @staticmethod
    def _looks_like_auth_page(url: str) -> bool:
        current = str(url or "").lower()
        auth_keywords = (
            "login",
            "signin",
            "sign-in",
            "register",
            "signup",
            "sign-up",
            "verification",
            "verify",
            "reset-password",
            "forgot-password",
        )
        return any(keyword in current for keyword in auth_keywords)

    @staticmethod
    def _same_page(left: str, right: str) -> bool:
        left_parsed = urlparse(left)
        right_parsed = urlparse(right)
        return (
            left_parsed.scheme == right_parsed.scheme
            and left_parsed.netloc == right_parsed.netloc
            and left_parsed.path == right_parsed.path
            and left_parsed.query == right_parsed.query
        )

    @staticmethod
    def _slugify(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "account"
