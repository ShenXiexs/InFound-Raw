"""Playwright runner for TikTok creator portal (login + filter + list)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from common.core.config import get_settings
from common.core.exceptions import PlaywrightError
from common.core.logger import get_logger
from apps.portal_tiktok_sample_crawler.services.login_manager import LoginManager
from apps.portal_tiktok_sample_crawler.services.email_verifier import GmailVerificationCode

settings = get_settings()
logger = get_logger()


@dataclass
class AccountProfile:
    name: str
    login_email: str
    login_password: Optional[str]
    gmail_username: str
    gmail_app_password: str
    region: str
    creator_id: Optional[str] = None
    enabled: bool = True


@dataclass
class CreatorSearchOptions:
    search_keywords_raw: str = ""
    search_keyword: str = ""
    product_categories: List[str] = field(default_factory=list)
    content_types: List[str] = field(default_factory=list)
    fans_age_range: List[str] = field(default_factory=list)
    fans_gender: Optional[str] = None
    fans_gender_percent: Optional[int] = None
    gmv_ranges: List[str] = field(default_factory=list)
    sales_ranges: List[str] = field(default_factory=list)
    min_engagement_rate: Optional[float] = None
    min_fans: Optional[int] = None
    avg_views: Optional[int] = None
    max_creators: Optional[int] = None


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items: List[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                items.append(text)
        return items
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


class CreatorCrawlerRunnerService:
    """Open TikTok Creator search page, apply filters, and load creator list."""

    def __init__(self, login_manager: Optional[LoginManager] = None) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._main_page: Optional[Page] = None
        self._initialize_lock = asyncio.Lock()
        self._run_lock = asyncio.Lock()

        self.headless = bool(getattr(settings, "PLAYWRIGHT_HEADLESS", True))
        self.target_url = getattr(
            settings,
            "CREATOR_TARGET_URL",
            "https://partner.tiktokshop.com/affiliate-cmp/creator?market=19",
        )
        self.login_url = getattr(
            settings,
            "CREATOR_LOGIN_URL",
            "https://partner-sso.tiktok.com/account/login?from=ttspc_logout&redirectURL=%2F%2Fpartner.tiktokshop.com%2Fhome&lang=en",
        )
        self.search_input_selector = getattr(
            settings,
            "CREATOR_SEARCH_INPUT_SELECTOR",
            'input[data-tid="m4b_input_search"]',
        )
        self.default_region = str(getattr(settings, "CREATOR_DEFAULT_REGION", "MX") or "MX").upper()
        self.account_config_path = Path(
            getattr(settings, "CREATOR_ACCOUNT_CONFIG_PATH", "configs/accounts.json")
        )
        self.default_max_creators = int(
            getattr(settings, "CREATOR_MAX_CREATOR_LOAD", 400) or 400
        )
        self.max_scroll_attempts = int(
            getattr(settings, "CREATOR_MAX_SCROLL_ATTEMPTS", 50) or 50
        )

        self.account_profile: Optional[AccountProfile] = None
        self.gmail_verifier: Optional[GmailVerificationCode] = None

        manual_login = bool(getattr(settings, "MANUAL_LOGIN_DEFAULT", False))
        manual_code_input = bool(getattr(settings, "MANUAL_EMAIL_CODE_INPUT", False))
        manual_code_timeout = int(
            getattr(settings, "MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS", 180) or 180
        )
        self.login_manager = login_manager or LoginManager(
            login_url=self.login_url,
            search_input_selector=self.search_input_selector,
            manual_login_default=manual_login,
            manual_email_code_input=manual_code_input,
            manual_email_code_input_timeout_seconds=manual_code_timeout,
        )

        self.accounts_data = self._load_accounts_config()

    def _load_accounts_config(self) -> List[Dict[str, Any]]:
        if not self.account_config_path.exists():
            return []
        try:
            with self.account_config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            accounts = data.get("accounts", [])
            return accounts if isinstance(accounts, list) else []
        except Exception as exc:
            logger.warning("Failed to load accounts config (%s): %s", self.account_config_path, exc)
            return []

    def resolve_profile(self, region: Optional[str], account_name: Optional[str]) -> AccountProfile:
        desired_region = (region or self.default_region or "MX").upper()
        if account_name:
            for account in self.accounts_data:
                if account_name.lower() == str(account.get("name", "")).lower():
                    if not account.get("enabled", True):
                        raise PlaywrightError(f"Account {account_name} is disabled")
                    return AccountProfile(
                        name=account.get("name", ""),
                        login_email=account.get("login_email", ""),
                        login_password=account.get("login_password"),
                        gmail_username=account.get("gmail_username", ""),
                        gmail_app_password=account.get("gmail_app_password", ""),
                        region=str(account.get("region", desired_region) or desired_region).upper(),
                        creator_id=account.get("creator_id"),
                        enabled=account.get("enabled", True),
                    )

        for account in self.accounts_data:
            if not account.get("enabled", True):
                continue
            if str(account.get("region", "")).upper() != desired_region:
                continue
            return AccountProfile(
                name=account.get("name", ""),
                login_email=account.get("login_email", ""),
                login_password=account.get("login_password"),
                gmail_username=account.get("gmail_username", ""),
                gmail_app_password=account.get("gmail_app_password", ""),
                region=desired_region,
                creator_id=account.get("creator_id"),
                enabled=account.get("enabled", True),
            )

        login_email = getattr(settings, "CREATOR_LOGIN_EMAIL", "")
        gmail_username = getattr(settings, "CREATOR_GMAIL_USERNAME", "")
        gmail_password = getattr(settings, "CREATOR_GMAIL_APP_PASSWORD", "")
        if not login_email or not gmail_username or not gmail_password:
            raise PlaywrightError("Creator crawler account credentials are missing")

        return AccountProfile(
            name=account_name or "default",
            login_email=login_email,
            login_password=getattr(settings, "CREATOR_LOGIN_PASSWORD", None),
            gmail_username=gmail_username,
            gmail_app_password=gmail_password,
            region=desired_region,
            creator_id=None,
            enabled=True,
        )

    def build_options(self, payload: Optional[Dict[str, Any]]) -> CreatorSearchOptions:
        data = payload if isinstance(payload, dict) else {}

        def pick(keys: List[str], default: Any) -> Any:
            for key in keys:
                if key in data and data[key] is not None:
                    return data[key]
            return default

        raw_keywords = pick(
            ["search_keywords", "searchKeywords", "keyword", "searchKeyword"],
            getattr(settings, "CREATOR_SEARCH_KEYWORDS", ""),
        )
        if isinstance(raw_keywords, list):
            raw = ", ".join(str(item).strip() for item in raw_keywords if str(item).strip())
            keyword = str(raw_keywords[0]).strip() if raw_keywords else ""
        else:
            raw = str(raw_keywords or "").strip()
            keyword = raw.split(",")[0].strip() if raw else ""

        product_categories = _normalize_list(
            pick(["product_category", "productCategory", "product_categories"],
                 getattr(settings, "CREATOR_PRODUCT_CATEGORIES", []))
        )
        content_types = _normalize_list(
            pick(["content_type", "contentType", "content_types"],
                 getattr(settings, "CREATOR_CONTENT_TYPES", []))
        )
        fans_age_range = _normalize_list(
            pick(["fans_age_range", "fansAgeRange", "age_range", "ageRange"],
                 getattr(settings, "CREATOR_FANS_AGE_RANGE", []))
        )
        fans_gender = pick(
            ["fans_gender", "fansGender", "gender"],
            getattr(settings, "CREATOR_FANS_GENDER", ""),
        )
        fans_gender = str(fans_gender).strip() if fans_gender else None
        fans_gender_percent = _parse_int(
            pick(
                ["fans_gender_percent", "fansGenderPercent", "gender_percent", "genderPercent"],
                getattr(settings, "CREATOR_FANS_GENDER_PERCENT", None),
            )
        )
        gmv_ranges = _normalize_list(
            pick(["gmv", "gmv_ranges", "gmvRanges"], getattr(settings, "CREATOR_GMV_RANGES", []))
        )
        sales_ranges = _normalize_list(
            pick(["sales", "sales_ranges", "salesRanges"], getattr(settings, "CREATOR_SALES_RANGES", []))
        )
        min_engagement_rate = _parse_float(
            pick(
                ["min_engagement_rate", "minEngagementRate", "engagement"],
                getattr(settings, "CREATOR_MIN_ENGAGEMENT_RATE", None),
            )
        )
        min_fans = _parse_int(
            pick(["min_fans", "minFans"], getattr(settings, "CREATOR_MIN_FANS", None))
        )
        avg_views = _parse_int(
            pick(["avg_views", "avgViews"], getattr(settings, "CREATOR_AVG_VIEWS", None))
        )
        max_creators = _parse_int(
            pick(["max_creators", "maxCreators"], getattr(settings, "CREATOR_MAX_CREATOR_LOAD", None))
        )

        return CreatorSearchOptions(
            search_keywords_raw=raw,
            search_keyword=keyword,
            product_categories=product_categories,
            content_types=content_types,
            fans_age_range=fans_age_range,
            fans_gender=fans_gender,
            fans_gender_percent=fans_gender_percent,
            gmv_ranges=gmv_ranges,
            sales_ranges=sales_ranges,
            min_engagement_rate=min_engagement_rate,
            min_fans=min_fans,
            avg_views=avg_views,
            max_creators=max_creators,
        )

    async def initialize(self, profile: AccountProfile) -> None:
        try:
            logger.info("Initializing Playwright", headless=self.headless)
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(
                viewport={"width": 1600, "height": 900},
                ignore_https_errors=True,
            )
            self._context.set_default_timeout(60_000)
            self._main_page = await self._context.new_page()
            self.account_profile = profile
            self.gmail_verifier = GmailVerificationCode(
                username=profile.gmail_username,
                app_password=profile.gmail_app_password,
            )
            await self._perform_login(self._main_page)
            await self._goto_creator_page(self._main_page, profile.region)
        except Exception as exc:
            await self.close()
            raise PlaywrightError("Playwright initialization failed") from exc

    async def ensure_ready(self, profile: AccountProfile) -> None:
        async with self._initialize_lock:
            if self._context and self._main_page and not self._main_page.is_closed():
                return
            await self.initialize(profile)

    async def close(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._main_page = None

    async def ensure_main_page(self) -> Page:
        if not self._context:
            raise PlaywrightError("Playwright context is not ready")
        if not self._main_page or self._main_page.is_closed():
            self._main_page = await self._context.new_page()
        return self._main_page

    async def _perform_login(self, page: Page) -> None:
        if not self.account_profile or not self.gmail_verifier:
            raise PlaywrightError("Account login context missing")
        await self.login_manager.perform_login(
            page=page,
            account_profile=self.account_profile,
            gmail_verifier=self.gmail_verifier,
        )

    async def _ensure_logged_in(self, page: Page) -> None:
        try:
            if await self.login_manager.is_logged_in(page):
                return
        except Exception:
            pass
        await self._perform_login(page)

    def _creator_url_for_region(self, region: Optional[str]) -> str:
        region_code = (region or self.default_region or "").upper()
        target = self.target_url
        if "partner.tiktokshop.com" in target and region_code.startswith("FR"):
            return target.replace("partner.tiktokshop.com", "partner.eu.tiktokshop.com")
        return target

    async def _goto_creator_page(self, page: Page, region: Optional[str]) -> None:
        target = self._creator_url_for_region(region)
        await page.goto(target, wait_until="networkidle", timeout=60_000)
        await page.wait_for_selector(self.search_input_selector, timeout=30_000)

    async def prewarm(self, region: Optional[str] = None, account_name: Optional[str] = None) -> None:
        async with self._run_lock:
            profile = self.resolve_profile(region=region, account_name=account_name)
            await self.ensure_ready(profile)
            page = await self.ensure_main_page()
            await self._ensure_logged_in(page)
            await self._goto_creator_page(page, profile.region)

    async def run_once(
        self,
        options: CreatorSearchOptions,
        *,
        region: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> List[str]:
        async with self._run_lock:
            profile = self.resolve_profile(region=region, account_name=account_name)
            await self.ensure_ready(profile)
            page = await self.ensure_main_page()
            await self._ensure_logged_in(page)
            await self._goto_creator_page(page, profile.region)

            logger.info("Applying creator filters", options=options)
            if not await self.apply_filters(page, options):
                raise PlaywrightError("Failed to apply creator filters")

            creators = await self.load_creators(page, max_creators=options.max_creators)
            logger.info("Creator list loaded", count=len(creators))
            return creators

    async def apply_filters(self, page: Page, options: CreatorSearchOptions) -> bool:
        try:
            await self._click_blank_area(page)

            if options.search_keyword:
                search_inputs = [
                    self.search_input_selector,
                    'input[placeholder*="Search"]',
                    'input[placeholder*="names"]',
                    'xpath=//*[@id="content-container"]//span/span/input',
                ]
                await self._fill_first(page, search_inputs, options.search_keyword, "search keyword")

            creators_panel_selectors = [
                'label:has(input[value="creator"]) button',
                'input[value="creator"] ~ button',
            ]

            if options.product_categories:
                for category in options.product_categories:
                    await self._ensure_panel_active(page, "Creators", creators_panel_selectors)
                    if await self._open_product_category(page):
                        await self._select_cascader_option(page, category)
                    await self._click_blank_area(page)

            if options.content_types:
                for content_type in options.content_types:
                    await self._ensure_panel_active(page, "Creators", creators_panel_selectors)
                    if await self._open_dropdown(
                        page,
                        [
                            'button:has(div:has-text("Content"))',
                            'button:has-text("Content type")',
                            'xpath=//button[.//div[contains(@class,"arco-typography")][contains(text(),"Content")]]',
                        ],
                        "Content type",
                    ):
                        await self._select_options_in_visible_popup(page, [content_type])
                    await self._click_blank_area(page)

            followers_panel_selectors = [
                'label:has(input[value="follower"]) button',
                'input[value="follower"] ~ button',
            ]

            if options.min_fans and options.min_fans > 0:
                await self._ensure_panel_active(page, "Followers", followers_panel_selectors)
                await self._click_first(
                    page,
                    [
                        'button:has(div:has-text("Follower count"))',
                        'button:has(div:has-text("Follower size"))',
                        'xpath=//button[.//div[contains(text(),"Follower count")]]',
                        'xpath=//button[.//div[contains(text(),"Follower size")]]',
                    ],
                    "Follower count",
                )
                await self._fill_first(
                    page,
                    [
                        'xpath=//*[@id="followerSize"]//input[1]',
                        'xpath=//*[@id="followerSize"]//span/div//div[1]/input[1]',
                        'xpath=//div[@id="followerSize"]//input[@type="text"][1]',
                    ],
                    str(options.min_fans),
                    "Follower min",
                )
                await self._click_blank_area(page)

            if options.fans_age_range:
                for age_range in options.fans_age_range:
                    await self._ensure_panel_active(page, "Followers", followers_panel_selectors)
                    if await self._open_dropdown(
                        page,
                        [
                            'button:has(div:has-text("Follower age"))',
                            'xpath=//button[.//div[contains(text(),"Follower age")]]',
                        ],
                        "Follower age",
                    ):
                        await self._select_options_in_visible_popup(page, [age_range])
                    await self._click_blank_area(page)

            if options.fans_gender:
                await self._ensure_panel_active(page, "Followers", followers_panel_selectors)
                if await self._open_dropdown(
                    page,
                    [
                        'button:has(div:has-text("Follower gend"))',
                        'xpath=//button[.//div[contains(text(),"Follower gend")]]',
                    ],
                    "Follower gender",
                ):
                    await self._select_options_in_visible_popup(page, [options.fans_gender])
                if options.fans_gender_percent:
                    await self._adjust_gender_slider(page, options.fans_gender_percent)
                await self._click_blank_area(page)

            performance_panel_selectors = ['button:has-text("Performance")']

            if options.gmv_ranges:
                for gmv in options.gmv_ranges:
                    await self._ensure_panel_active(page, "Performance", performance_panel_selectors)
                    if await self._open_dropdown(
                        page,
                        [
                            '#gmv button',
                            'button:has(div:has-text("GMV"))',
                            'xpath=//button[.//div[contains(text(),"GMV")]]',
                        ],
                        "GMV",
                    ):
                        await self._select_options_in_visible_popup(page, [gmv])
                    await self._click_blank_area(page)

            if options.sales_ranges:
                for sales in options.sales_ranges:
                    await self._ensure_panel_active(page, "Performance", performance_panel_selectors)
                    if await self._open_dropdown(
                        page,
                        [
                            '#unitsSold button',
                            'button:has(div:has-text("Items so"))',
                            'button:has(div:has-text("Items sold"))',
                            'xpath=//button[.//div[contains(text(),"Items so")]]',
                        ],
                        "Items sold",
                    ):
                        await self._select_options_in_visible_popup(page, [sales])
                    await self._click_blank_area(page)

            if options.avg_views and options.avg_views > 0:
                await self._ensure_panel_active(page, "Performance", performance_panel_selectors)
                await self._click_first(
                    page,
                    [
                        'button:has(div:has-text("Average views per video"))',
                        'xpath=//button[.//div[contains(@class,"arco-typography")][normalize-space(text())="Average views per video"]]',
                    ],
                    "Average views per video",
                )
                await self._fill_first(
                    page,
                    [
                        'xpath=//*[@id="filter-container"]/div[2]/span/div/div[1]/input',
                        'input[data-tid="m4b_input"]:visible',
                        'input[type="text"]:visible',
                    ],
                    str(options.avg_views),
                    "Average views min",
                )
                await self._click_blank_area(page)

            if options.min_engagement_rate and options.min_engagement_rate > 0:
                await self._ensure_panel_active(page, "Performance", performance_panel_selectors)
                await self._click_first(
                    page,
                    [
                        'button:has(div:has-text("Engagement rate"))',
                        'xpath=//button[.//div[contains(@class,"arco-typography")][normalize-space(text())="Engagement rate"]]',
                    ],
                    "Engagement rate",
                )
                await self._fill_first(
                    page,
                    [
                        'xpath=//*[@id="filter-container"]/div[2]/span/div/div[1]/div/span/span/input',
                        'input[data-tid="m4b_input"]:visible',
                        'input[type="text"]:visible',
                    ],
                    str(options.min_engagement_rate),
                    "Engagement rate min",
                )
                await self._click_blank_area(page)

            if not await self._click_first(
                page,
                [
                    'button:has(svg.arco-icon-search)',
                    'svg.arco-icon-search',
                    'button:has([class*="search"])',
                    'xpath=//button[.//svg[contains(@class,"search")]]',
                ],
                "Search",
            ):
                return False

            await self._wait_spinner_done(page)
            return True
        except Exception as exc:
            logger.warning("Apply filters failed: %s", exc)
            return False

    async def load_creators(self, page: Page, max_creators: Optional[int]) -> List[str]:
        target = max_creators or self.default_max_creators
        if target <= 0:
            target = self.default_max_creators

        creators: List[str] = []
        seen = set()
        no_new_count = 0

        for attempt in range(self.max_scroll_attempts):
            current = await self._collect_creator_names(page)
            new_names = [name for name in current if name not in seen]
            for name in new_names:
                seen.add(name)
                creators.append(name)

            logger.info(
                "Creator list scroll",
                attempt=attempt + 1,
                new=len(new_names),
                total=len(creators),
            )

            if len(creators) >= target:
                break
            if not new_names:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            await self._scroll_creator_list(page)
            await page.wait_for_timeout(1500)

        return creators

    async def _collect_creator_names(self, page: Page) -> List[str]:
        selectors = [
            'span[data-e2e="fbc99397-6043-1b37"]',
            'div[class*="creator-card"] span',
            'div[class*="creator-item"] span',
        ]
        names: List[str] = []
        for selector in selectors:
            locator = page.locator(selector)
            try:
                if await locator.count() == 0:
                    continue
                texts = await locator.all_text_contents()
                for text in texts:
                    clean = text.strip()
                    if clean:
                        names.append(clean)
                if names:
                    break
            except Exception:
                continue
        return names

    async def _scroll_creator_list(self, page: Page) -> None:
        scroll_candidates = [
            'div[class*="arco-table-body"]',
            'div[class*="table-body"]',
            'div[class*="virtual-list"]',
            'div[class*="scroll"]',
        ]
        for selector in scroll_candidates:
            locator = page.locator(selector).first
            try:
                if await locator.count() == 0:
                    continue
                await locator.evaluate("(el) => { el.scrollTop = el.scrollHeight; }")
                return
            except Exception:
                continue
        try:
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
        except Exception:
            pass

    async def _click_blank_area(self, page: Page) -> None:
        try:
            await page.mouse.click(500, 200)
            await page.wait_for_timeout(300)
        except Exception:
            pass

    async def _click_first(self, page: Page, selectors: List[str], desc: str, timeout: int = 15000) -> bool:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() > 0 and await locator.is_enabled():
                    await locator.click(timeout=timeout, force=True)
                    logger.debug("Clicked %s via %s", desc, selector)
                    return True
            except Exception:
                continue
        logger.warning("Failed to click %s", desc)
        return False

    async def _fill_first(self, page: Page, selectors: List[str], value: str, desc: str) -> bool:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() > 0 and await locator.is_enabled():
                    await locator.click(timeout=8000)
                    await locator.fill(str(value))
                    logger.debug("Filled %s via %s", desc, selector)
                    return True
            except Exception:
                continue
        logger.warning("Failed to fill %s", desc)
        return False

    async def _open_dropdown(self, page: Page, selectors: List[str], desc: str) -> bool:
        if not await self._click_first(page, selectors, desc, timeout=5000):
            return False
        try:
            await page.locator(
                'xpath=//div[starts-with(@id,"arco-select-popup") and not(contains(@style,"display: none"))]'
            ).first.wait_for(state="visible", timeout=5000)
        except Exception:
            pass
        return True

    async def _select_options_in_visible_popup(self, page: Page, option_texts: List[str]) -> List[str]:
        chosen: List[str] = []
        for text in option_texts:
            if not text:
                continue
            option = page.locator(
                f'xpath=//li[@role="option" and contains(@class, "arco-select-option")]'
                f'[.//text()[contains(normalize-space(.), "{text}")]]'
            ).first
            try:
                if await option.count() == 0:
                    continue
                try:
                    await option.scroll_into_view_if_needed(timeout=800)
                except Exception:
                    pass
                await option.click(force=True, timeout=3000)
                chosen.append(text)
                await page.wait_for_timeout(200)
            except Exception:
                continue
        return chosen

    async def _open_product_category(self, page: Page) -> bool:
        return await self._click_first(
            page,
            [
                'button:has(div:has-text("Product category"))',
                'button:has-text("Product category")',
                'xpath=//button[.//div[contains(@class,"arco-typography")][contains(text(),"Product category")]]',
            ],
            "Product category",
        )

    async def _select_cascader_option(self, page: Page, category: str) -> bool:
        if not category:
            return False
        try:
            await page.locator("ul.arco-cascader-list").first.wait_for(state="visible", timeout=5000)
        except Exception:
            return False
        option = page.locator(f'ul.arco-cascader-list li:has-text("{category}")').first
        try:
            if await option.count() == 0:
                return False
            await option.scroll_into_view_if_needed()
            await option.click(force=True)
            return True
        except Exception:
            return False

    async def _adjust_gender_slider(self, page: Page, percentage: int) -> None:
        try:
            slider_button = page.locator('//div[@id="followerGender"]//div[@role="slider"]').first
            slider_track = page.locator(
                '//div[@id="followerGender"]//div[contains(@class,"arco-slider-road")]'
            ).first
            button_box = await slider_button.bounding_box()
            track_box = await slider_track.bounding_box()
            if not button_box or not track_box:
                return
            target_x = track_box["x"] + track_box["width"] * (percentage / 100.0)
            center_y = track_box["y"] + (track_box["height"] / 2)
            await page.mouse.move(button_box["x"] + button_box["width"] / 2, center_y)
            await page.mouse.down()
            await page.mouse.move(target_x, center_y, steps=10)
            await page.mouse.up()
        except Exception:
            return

    async def _ensure_panel_active(self, page: Page, panel_name: str, selectors: List[str]) -> None:
        await self._click_first(page, selectors, f"{panel_name} panel")

    async def _wait_spinner_done(self, page: Page, max_ms: int = 15000) -> None:
        try:
            await page.locator('[class*="arco-spin"], [class*="arco-spin-loading"]').wait_for(
                state="hidden",
                timeout=max_ms,
            )
        except Exception:
            pass
