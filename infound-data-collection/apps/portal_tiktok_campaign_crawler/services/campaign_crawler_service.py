from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pandas as pd
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from common.core.config import get_settings
from common.core.exceptions import MessageProcessingError, PlaywrightError
from common.core.logger import get_logger
from apps.portal_tiktok_sample_crawler.services.email_verifier import GmailVerificationCode
from .campaign_ingestion_client import CampaignIngestionClient

logger = get_logger()


async def _close_with_timeout(resource: Any, name: str, timeout: float = 3.0) -> None:
    if not resource:
        return
    close_fn = getattr(resource, "aclose", None) or getattr(resource, "close", None) or getattr(
        resource, "stop", None
    )
    if not close_fn:
        return
    try:
        await asyncio.wait_for(close_fn(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Close timed out", resource=name)
    except Exception:
        logger.warning("Close failed", resource=name, exc_info=True)


@dataclass
class CampaignCrawlOptions:
    region: str
    account_name: Optional[str] = None
    campaign_ids: List[str] = field(default_factory=list)
    scan_all_pages: bool = True
    max_pages: Optional[int] = None
    export_excel: bool = False


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


class CampaignCrawlerService:
    """Campaign crawler that validates TikTok Shop Partner Center login."""

    EXPORT_COLUMNS = [
        "campaign_id",
        "campaign_name",
        "campaign_status",
        "campaign_registration_period",
        "campaign_period",
        "campaign_pending_products",
        "campaign_approved_products",
        "product_id",
        "product_name",
        "date_registered",
        "commission_rate",
        "sale_price_min",
        "sale_price_max",
        "stock",
        "available_sample",
        "product_rating",
        "items_sold",
        "reviews_count",
        "shop_name",
        "shop_phone",
        "shop_code",
        "data_page_url",
        "detail_page_url",
        "crawl_timestamp",
        "image_link",
    ]
    APPROVED_TAB_TEXTS = ("Approved",)
    VIEW_DETAILS_TEXTS = ("View details", "View Details")
    VIEW_DATA_TEXTS = ("View data", "View Data")

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.headless = bool(getattr(self.settings, "PLAYWRIGHT_HEADLESS", True))

        self.default_region = str(
            getattr(self.settings, "CAMPAIGN_DEFAULT_REGION", "MX") or "MX"
        ).upper()

        self.login_email = str(getattr(self.settings, "CAMPAIGN_LOGIN_EMAIL", "") or "").strip()
        self.gmail_username = str(
            getattr(self.settings, "CAMPAIGN_GMAIL_USERNAME", "") or ""
        ).strip()
        self.gmail_app_password = str(
            getattr(self.settings, "CAMPAIGN_GMAIL_APP_PASSWORD", "") or ""
        ).strip()
        self.manual_email_code_input = bool(
            getattr(self.settings, "CAMPAIGN_MANUAL_EMAIL_CODE_INPUT", False)
        )
        self.manual_email_code_input_timeout_seconds = int(
            getattr(self.settings, "CAMPAIGN_MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS", 180) or 180
        )
        self.manual_login_default = bool(
            getattr(self.settings, "CAMPAIGN_MANUAL_LOGIN", False)
        )
        self.manual_login_timeout_seconds = int(
            getattr(self.settings, "CAMPAIGN_MANUAL_LOGIN_TIMEOUT_SECONDS", 300) or 300
        )
        self.home_wait_timeout_seconds = int(
            getattr(self.settings, "CAMPAIGN_HOME_WAIT_TIMEOUT_SECONDS", 60) or 60
        )
        self.login_url_override = str(
            getattr(self.settings, "CAMPAIGN_LOGIN_URL", "") or ""
        ).strip()
        self.account_config_path = getattr(
            self.settings, "CAMPAIGN_ACCOUNT_CONFIG_PATH", "configs/accounts.json"
        )
        self.target_url = str(getattr(self.settings, "CAMPAIGN_TARGET_URL", "") or "").strip()
        self.export_excel_enabled = bool(
            getattr(self.settings, "CAMPAIGN_ENABLE_EXCEL_EXPORT", False)
        )
        self.export_dir = Path(
            getattr(self.settings, "CAMPAIGN_EXPORT_DIR", "data/manage_campaign")
        )
        self.max_pages_default = int(getattr(self.settings, "CAMPAIGN_MAX_PAGES", 0) or 0)

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._export_path: Optional[Path] = None

        self.accounts_data = self._load_accounts_config()
        self.account_profile: Optional[AccountProfile] = None
        self.source = "portal_tiktok_campaign_crawler"
        self.task_id: Optional[str] = None
        self.operator_id: Optional[str] = None

        self.gmail_verifier: Optional[GmailVerificationCode] = None
        if self.gmail_username and self.gmail_app_password:
            self.gmail_verifier = GmailVerificationCode(
                self.gmail_username, self.gmail_app_password
            )

        inner_api_token = getattr(self.settings, "INNER_API_AUTH_TOKEN", None)
        if not inner_api_token:
            valid_tokens = getattr(self.settings, "INNER_API_AUTH_VALID_TOKENS", []) or []
            inner_api_token = valid_tokens[0] if valid_tokens else None
        self.ingestion_client = CampaignIngestionClient(
            base_url=self.settings.INNER_API_BASE_URL,
            campaign_path=self.settings.INNER_API_CAMPAIGN_PATH,
            product_path=self.settings.INNER_API_PRODUCT_PATH,
            header_name=self.settings.INNER_API_AUTH_REQUIRED_HEADER,
            token=inner_api_token,
            timeout=float(self.settings.INNER_API_TIMEOUT),
        )

    def _partner_domain(self) -> str:
        region = (self.default_region or "").strip().upper()
        if region in {"FR", "ES"}:
            return "partner.eu.tiktokshop.com"
        return "partner.tiktokshop.com"

    def _login_url(self) -> str:
        if self.login_url_override:
            return self.login_url_override
        redirect_host = self._partner_domain()
        return (
            "https://partner-sso.tiktok.com/account/login"
            "?from=ttspc_logout"
            f"&redirectURL=%2F%2F{redirect_host}%2Fhome"
            "&lang=en"
            "&local_id=localID_Portal_88574979_1758691471679"
            "&userID=51267627"
            "&is_through_login=1"
        )

    async def initialize(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()
        self.logger.info(
            "Playwright session initialized",
            headless=self.headless,
            login_email=self.login_email or None,
            region=self.default_region,
        )

    async def _prompt_verification_code(self) -> Optional[str]:
        if not self.manual_email_code_input:
            return None
        prompt = "Enter TikTok email verification code (6 chars), or empty to skip: "
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(input, prompt),
                timeout=float(self.manual_email_code_input_timeout_seconds),
            )
        except asyncio.TimeoutError:
            self.logger.warning("Manual verification input timed out")
            return None
        except EOFError:
            self.logger.warning("Manual verification input unavailable")
            return None
        except Exception as exc:
            self.logger.warning("Manual verification input failed", error=str(exc))
            return None

        code = str(raw or "").strip().upper()
        if not code:
            return None
        if not re.fullmatch(r"[A-Z0-9]{6}", code):
            self.logger.warning("Manual verification code format invalid")
            return None
        return code

    async def _wait_for_manual_login(self, page) -> None:
        self.logger.info("Manual login enabled; please complete login in the browser")
        start = asyncio.get_event_loop().time()
        timeout = float(self.manual_login_timeout_seconds)
        while (asyncio.get_event_loop().time() - start) < timeout:
            try:
                if await self._is_logged_in(page):
                    self.logger.info("Manual login detected")
                    return
            except Exception:
                pass
            await asyncio.sleep(2)
        raise PlaywrightError("Manual login timeout")

    async def _wait_for_home_ready(self, page) -> None:
        timeout = float(self.home_wait_timeout_seconds)
        start = asyncio.get_event_loop().time()
        markers = [
            'input[data-tid="m4b_input_search"]',
            'text="Welcome to TikTok Shop Partner Center"',
            'text="Account GMV trend"',
            'text="View your data and facilitate seller authorizations"',
            'div.index__sideMenu--K7BH0',
            'span:has-text("Campaigns")',
        ]
        while (asyncio.get_event_loop().time() - start) < timeout:
            try:
                await page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                pass
            for selector in markers:
                try:
                    await page.wait_for_selector(selector, timeout=1_000)
                    self.logger.info("Home page ready", marker=selector)
                    return
                except Exception:
                    continue
            await asyncio.sleep(1)
        raise PlaywrightError("Home page not ready")

    async def _is_logged_in(self, page) -> bool:
        host = (urlparse(page.url or "").hostname or "").lower()
        if not (
            host.endswith("partner.tiktokshop.com")
            or host.endswith("partner.eu.tiktokshop.com")
            or "partner" in host
        ):
            return False
        markers = [
            'input[data-tid="m4b_input_search"]',
            'text="Welcome to TikTok Shop Partner Center"',
            'text="Account GMV trend"',
            'text="View your data and facilitate seller authorizations"',
            'text="Hi"',
        ]
        for selector in markers:
            try:
                await page.wait_for_selector(selector, timeout=2_000)
                return True
            except Exception:
                continue
        path = (urlparse(page.url or "").path or "").lower()
        return "login" not in path

    async def login(self, page) -> bool:
        if not self.manual_login_default and not self.login_email:
            raise PlaywrightError("CAMPAIGN_LOGIN_EMAIL is required")
        if not self.manual_login_default and not self.manual_email_code_input and not self.gmail_verifier:
            raise PlaywrightError("Gmail verifier or manual code input is required")

        max_retries = 5
        for attempt in range(max_retries):
            self.logger.info("Login attempt", attempt=attempt + 1, max_retries=max_retries)
            try:
                await page.goto(self._login_url(), wait_until="networkidle")
                if await self._is_logged_in(page):
                    self.logger.info("Already logged in")
                    return True

                if self.manual_login_default:
                    await self._wait_for_manual_login(page)
                    return True

                email_login_btn = page.get_by_text("Log in with code").first
                await email_login_btn.click()

                await page.fill("#email input", self.login_email)

                try:
                    send_code_btn = page.locator(
                        'div[starling-key="profile_edit_userinfo_send_code"]'
                    ).first
                    await send_code_btn.wait_for(state="visible", timeout=5000)
                    await send_code_btn.click()
                    self.logger.info("Clicked Send code")
                except Exception as exc:
                    self.logger.warning("Failed to click Send code", error=str(exc))

                verification_code = None
                if self.manual_email_code_input:
                    verification_code = await self._prompt_verification_code()
                    if not verification_code:
                        self.logger.error("Manual verification code missing")
                        continue
                else:
                    verification_code = await asyncio.to_thread(
                        self.gmail_verifier.get_verification_code
                    )

                if not verification_code:
                    self.logger.error("Failed to fetch verification code")
                    continue

                await page.fill("#emailCode_input", verification_code)

                login_btn = page.locator(
                    'button[starling-key="account_login_btn_loginform_login_text"]'
                ).first
                await login_btn.click()

                await page.wait_for_timeout(5000)
                if await self._is_logged_in(page):
                    self.logger.info("Login successful")
                    return True
                self.logger.error("Login submitted but markers not found")
                await asyncio.sleep(3)
            except PlaywrightTimeoutError:
                self.logger.error("Login page not loaded within timeout")
            except Exception as exc:
                self.logger.error("Login attempt failed", error=str(exc))
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)

        self.logger.error("Login failed after retries")
        return False

    def _normalized_region(self, region: Optional[str]) -> str:
        value = (region or self.default_region or "MX").strip().upper()
        return value or "MX"

    def _derive_campaign_url(self, page_url: str) -> Optional[str]:
        parsed = urlparse(page_url or "")
        if not parsed.scheme or not parsed.netloc:
            return None
        base = f"{parsed.scheme}://{parsed.netloc}"
        return f"{base}/affiliate-campaign/campaign"

    def _ensure_task_id(self) -> str:
        if not self.task_id:
            self.task_id = str(uuid.uuid4()).upper()
        return self.task_id

    def _build_ingestion_options(self, options: CampaignCrawlOptions) -> Dict[str, Any]:
        return {
            "account_name": self.account_profile.name if self.account_profile else None,
            "region": options.region,
            "campaign_ids": options.campaign_ids,
            "scan_all_pages": options.scan_all_pages,
            "max_pages": options.max_pages,
        }

    def _normalize_campaign_row(
        self,
        campaign_meta: Dict[str, Any],
        product_row: Dict[str, Any],
        options: CampaignCrawlOptions,
    ) -> Dict[str, Any]:
        return {
            "platform": "tiktok",
            "platform_campaign_id": campaign_meta.get("campaign_id") or "",
            "platform_campaign_name": campaign_meta.get("campaign_name") or "",
            "region": options.region,
            "status": campaign_meta.get("campaign_status") or "",
            "registration_period": campaign_meta.get("campaign_registration_period") or "",
            "campaign_period": campaign_meta.get("campaign_period") or "",
            "pending_product_count": campaign_meta.get("campaign_pending_products"),
            "approved_product_count": campaign_meta.get("campaign_approved_products"),
            "date_registered": product_row.get("date_registered"),
            "commission_rate": product_row.get("commission_rate"),
            "platform_shop_name": product_row.get("shop_name") or "",
            "platform_shop_phone": product_row.get("shop_phone") or "",
            "platform_shop_id": product_row.get("shop_code") or "",
        }

    def _normalize_product_row(
        self,
        row: Dict[str, Any],
        options: CampaignCrawlOptions,
    ) -> Dict[str, Any]:
        return {
            "platform": "tiktok",
            "platform_campaign_id": row.get("campaign_id") or "",
            "region": options.region,
            "platform_shop_name": row.get("shop_name") or "",
            "platform_shop_phone": row.get("shop_phone") or "",
            "platform_shop_id": row.get("shop_code") or "",
            "thumbnail": row.get("image_link") or "",
            "product_name": row.get("product_name") or "",
            "platform_product_id": row.get("product_id") or "",
            "product_rating": row.get("product_rating"),
            "reviews_count": row.get("reviews_count"),
            "product_sku": row.get("product_sku") or "",
            "stock": row.get("stock"),
            "available_sample_count": row.get("available_sample"),
            "item_sold": row.get("items_sold"),
            "sale_price_min": row.get("sale_price_min"),
            "sale_price_max": row.get("sale_price_max"),
        }

    async def _ingest_campaign_products(
        self,
        campaign_meta: Dict[str, Any],
        products: List[Dict[str, Any]],
        options: CampaignCrawlOptions,
    ) -> None:
        if not products:
            return
        operator_id = self.operator_id or self._ensure_task_id()
        campaign_row = self._normalize_campaign_row(campaign_meta, products[0], options)
        product_rows = [self._normalize_product_row(row, options) for row in products]
        options_payload = self._build_ingestion_options(options)
        await self.ingestion_client.submit_campaigns(
            source=self.source,
            operator_id=operator_id,
            options=options_payload,
            rows=[campaign_row],
        )
        await self.ingestion_client.submit_products(
            source=self.source,
            operator_id=operator_id,
            options=options_payload,
            rows=product_rows,
        )

    def _pick(self, body: Dict[str, Any], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in body and body[key] is not None:
                return body[key]
        return default

    def _coerce_positive_int(self, value: Any) -> Optional[int]:
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            return None
        return coerced if coerced > 0 else None

    def _parse_campaign_ids(self, body: Dict[str, Any]) -> List[str]:
        raw_ids: List[str] = []
        raw_list = self._pick(
            body,
            "campaign_ids",
            "campaignIds",
            "campaignIdList",
            "campaign_id_list",
        )
        if isinstance(raw_list, list):
            raw_ids.extend([str(item).strip() for item in raw_list if str(item).strip()])
        elif isinstance(raw_list, str):
            parts = [part.strip() for part in re.split(r"[,\s]+", raw_list) if part.strip()]
            raw_ids.extend(parts)

        single = self._pick(body, "campaign_id", "campaignId")
        if single:
            raw_ids.append(str(single).strip())

        seen = set()
        cleaned: List[str] = []
        for cid in raw_ids:
            if cid and cid not in seen:
                seen.add(cid)
                cleaned.append(cid)
        return cleaned

    def _parse_options(self, body: Dict[str, Any]) -> CampaignCrawlOptions:
        campaign_ids = self._parse_campaign_ids(body)
        account_name = self._pick(body, "account_name", "accountName")
        scan_all_pages = self._pick(body, "scan_all_pages", "scanAllPages")
        if scan_all_pages is None:
            scan_all_pages = not bool(campaign_ids)
        else:
            scan_all_pages = bool(scan_all_pages)

        max_pages = self._coerce_positive_int(self._pick(body, "max_pages", "maxPages"))
        if max_pages is None and self.max_pages_default > 0:
            max_pages = self.max_pages_default

        export_excel = self._pick(body, "export_excel", "exportExcel")
        if export_excel is None:
            export_excel = self.export_excel_enabled
        else:
            export_excel = bool(export_excel)

        region = self._normalized_region(self._pick(body, "region", "Region"))
        return CampaignCrawlOptions(
            region=region,
            account_name=account_name,
            campaign_ids=campaign_ids,
            scan_all_pages=scan_all_pages,
            max_pages=max_pages,
            export_excel=export_excel,
        )

    def _load_accounts_config(self) -> List[Dict[str, Any]]:
        path = Path(self.account_config_path)
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            accounts = data.get("accounts", [])
            return accounts if isinstance(accounts, list) else []
        except Exception as exc:
            self.logger.warning("Failed to load accounts config", path=str(path), error=str(exc))
            return []

    def _select_account(self, region: str, account_name: Optional[str]) -> AccountProfile:
        desired_region = (region or self.default_region or "MX").upper()
        if account_name:
            for account in self.accounts_data:
                if account_name.lower() == str(account.get("name", "")).lower():
                    enabled = account.get("enabled", True)
                    if not enabled:
                        raise PlaywrightError(f"Account {account_name} is disabled")
                    return AccountProfile(
                        name=account.get("name", ""),
                        login_email=account.get("login_email", ""),
                        login_password=account.get("login_password"),
                        gmail_username=account.get("gmail_username", ""),
                        gmail_app_password=account.get("gmail_app_password", ""),
                        region=str(account.get("region", self.default_region)).upper(),
                        creator_id=account.get("creator_id"),
                        enabled=enabled,
                    )
            raise PlaywrightError(f"Account {account_name} not found in config")

        for account in self.accounts_data:
            account_region = str(account.get("region", "")).upper()
            enabled = account.get("enabled", True)
            if enabled and account_region == desired_region:
                return AccountProfile(
                    name=account.get("name", ""),
                    login_email=account.get("login_email", ""),
                    login_password=account.get("login_password"),
                    gmail_username=account.get("gmail_username", ""),
                    gmail_app_password=account.get("gmail_app_password", ""),
                    region=account_region,
                    creator_id=account.get("creator_id"),
                    enabled=enabled,
                )

        for account in self.accounts_data:
            if account.get("enabled", True):
                return AccountProfile(
                    name=account.get("name", ""),
                    login_email=account.get("login_email", ""),
                    login_password=account.get("login_password"),
                    gmail_username=account.get("gmail_username", ""),
                    gmail_app_password=account.get("gmail_app_password", ""),
                    region=str(account.get("region", desired_region)).upper(),
                    creator_id=account.get("creator_id"),
                    enabled=True,
                )

        return AccountProfile(
            name="default",
            login_email=self.login_email,
            login_password=None,
            gmail_username=self.gmail_username,
            gmail_app_password=self.gmail_app_password,
            region=desired_region,
            creator_id=None,
            enabled=True,
        )

    def _resolve_account(self, options: CampaignCrawlOptions) -> None:
        profile = self._select_account(options.region, options.account_name)
        self.account_profile = profile
        self.operator_id = str(profile.creator_id or "").strip() or None
        if profile.login_email:
            self.login_email = profile.login_email
        if profile.gmail_username:
            self.gmail_username = profile.gmail_username
        if profile.gmail_app_password:
            self.gmail_app_password = profile.gmail_app_password
        self.default_region = profile.region or self.default_region
        if self.gmail_username and self.gmail_app_password:
            self.gmail_verifier = GmailVerificationCode(
                self.gmail_username, self.gmail_app_password
            )

    async def _wait_campaign_table(self, page) -> int:
        self.logger.info("Waiting for campaign table")
        try:
            await page.wait_for_selector(".arco-spin, .ant-spin", state="detached", timeout=9000)
        except Exception:
            pass
        rows = page.locator("tr.arco-table-tr")
        count = await rows.count()
        if count == 0:
            rows = page.locator("table tbody tr")
            count = await rows.count()
        self.logger.info("Campaign table rows", count=count)
        return count

    async def _wait_products_table(self, page) -> int:
        self.logger.info("Waiting for products table")
        try:
            await page.wait_for_selector(".arco-spin, .ant-spin", state="detached", timeout=9000)
        except Exception:
            pass
        for sel in ["tr.arco-table-tr", "table tbody tr", "tr[role=row]"]:
            rows = page.locator(sel)
            if await rows.count():
                self.logger.info("Products rows found", selector=sel, count=await rows.count())
                return await rows.count()
        self.logger.warning("Products table not found")
        return 0

    async def _navigate_to_my_campaign(self, page) -> bool:
        self.logger.info("Navigating to My campaigns")
        if self.target_url:
            try:
                self.logger.info("Opening campaign target url", url=self.target_url)
                await page.goto(self.target_url, wait_until="networkidle")
                if await self._wait_campaign_table(page) > 0:
                    return True
            except Exception as exc:
                self.logger.warning("Failed to open campaign target url", error=str(exc))
        else:
            derived_url = self._derive_campaign_url(page.url)
            if derived_url:
                try:
                    self.logger.info("Opening derived campaign url", url=derived_url)
                    await page.goto(derived_url, wait_until="networkidle")
                    if await self._wait_campaign_table(page) > 0:
                        return True
                except Exception as exc:
                    self.logger.warning("Failed to open derived campaign url", error=str(exc))

        try:
            got_it_btn = page.locator("button:has-text('Got it')").first
            if await got_it_btn.count() and await got_it_btn.is_visible():
                await got_it_btn.click()
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        menu_clicked = False
        # 先尝试直接点击左侧 Campaign 图标（页面结构更稳定）
        campaign_icon_selector = (
            "#root > div > div.index__content--sl5LM.ttspc-row > div.index__sideMenu--K7BH0 "
            "> div > div.index__menuList--hV6LD > div > div:nth-child(6) > div"
        )
        try:
            icon = page.locator(campaign_icon_selector).first
            if await icon.count():
                await icon.click()
                menu_clicked = True
                await page.wait_for_timeout(1500)
        except Exception:
            pass

        if not menu_clicked:
            for label in ("Campaigns", "Campaign"):
                candidate = page.locator(f"span:has-text('{label}')").first
                if await candidate.count():
                    try:
                        await candidate.click()
                        menu_clicked = True
                        await page.wait_for_timeout(1500)
                        break
                    except Exception:
                        continue

        if not menu_clicked:
            self.logger.warning("Campaigns menu not found")

        my_campaign_clicked = False
        for label in ("My campaigns", "My Campaigns"):
            candidate = page.locator(f"span:has-text('{label}')").first
            if await candidate.count():
                try:
                    await candidate.click()
                    my_campaign_clicked = True
                    await page.wait_for_timeout(2000)
                    break
                except Exception:
                    continue

        if not my_campaign_clicked:
            self.logger.error("My campaigns menu not found")
            return False

        self.logger.info("My campaigns clicked; waiting for table")
        return await self._wait_campaign_table(page) > 0

    async def _apply_campaign_search(self, page, campaign_id: str) -> bool:
        self.logger.info("Searching campaign", campaign_id=campaign_id)
        selectors = [
            'input[placeholder="Search campaign ID"]',
            'input[placeholder*="Search"]',
            'input[data-tid="m4b_input_search"]',
        ]
        for selector in selectors:
            loc = page.locator(selector)
            if await loc.count():
                target = loc.nth(1) if await loc.count() > 1 else loc.first
                try:
                    await target.fill("")
                    await target.fill(campaign_id)
                    await target.press("Enter")
                    await page.wait_for_timeout(2000)
                    return True
                except Exception:
                    continue
        return False

    async def _parse_campaign_row(self, row) -> Dict[str, Any]:
        tds = row.locator("td")
        if await tds.count() < 7:
            return {}

        col0 = (await tds.nth(0).inner_text()).strip()
        lines0 = [line.strip() for line in col0.splitlines() if line.strip()]
        campaign_name = lines0[0] if lines0 else ""
        match = re.search(r"ID\s*:?\s*([0-9]+)", col0)
        campaign_id = match.group(1) if match else ""

        status_text = (await tds.nth(1).inner_text()).strip()
        status_lines = [line.strip() for line in status_text.splitlines() if line.strip()]
        campaign_status = status_lines[0] if status_lines else status_text

        reg_text = (await tds.nth(3).inner_text()).replace("\n", "").replace(" ", "")
        period_text = (await tds.nth(4).inner_text()).replace("\n", "").replace(" ", "")
        pending_text = (await tds.nth(5).inner_text()).strip()
        approved_text = (await tds.nth(6).inner_text()).strip()

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "campaign_status": campaign_status,
            "campaign_registration_period": reg_text,
            "campaign_period": period_text,
            "campaign_pending_products": pending_text,
            "campaign_approved_products": approved_text,
        }

    async def _find_view_buttons(self, row) -> Tuple[Optional[Any], Optional[Any]]:
        detail_btn = None
        data_btn = None
        for label in self.VIEW_DETAILS_TEXTS:
            candidate = row.get_by_text(label, exact=False).first
            if await candidate.count():
                detail_btn = candidate
                break
        for label in self.VIEW_DATA_TEXTS:
            candidate = row.get_by_text(label, exact=False).first
            if await candidate.count():
                data_btn = candidate
                break

        if detail_btn or data_btn:
            return detail_btn, data_btn

        links = row.locator(
            "span.arco-link, a.arco-link, span.m4b-link, a.m4b-link, [data-tid='m4b_link']"
        )
        count = await links.count()
        for idx in range(count):
            item = links.nth(idx)
            try:
                text = (await item.inner_text()).strip()
            except Exception:
                continue
            if any(label in text for label in self.VIEW_DETAILS_TEXTS) and detail_btn is None:
                detail_btn = item
            if any(label in text for label in self.VIEW_DATA_TEXTS) and data_btn is None:
                data_btn = item
        return detail_btn, data_btn

    async def _capture_view_data(self, page, data_btn) -> str:
        before_url = page.url
        data_page_url = ""
        popup_page = None
        try:
            self.logger.info("Opening View data")
            async with page.context.expect_page(timeout=2000) as popup_info:
                await data_btn.click()
            popup_page = await popup_info.value
            await popup_page.wait_for_load_state("domcontentloaded", timeout=5000)
            data_page_url = popup_page.url
        except PlaywrightTimeoutError:
            await page.wait_for_timeout(1000)
            if page.url != before_url:
                data_page_url = page.url
        except Exception as exc:
            self.logger.warning("View data click failed", error=str(exc))
        finally:
            if popup_page:
                try:
                    await popup_page.close()
                except Exception:
                    pass

        if data_page_url and page.url != before_url:
            try:
                self.logger.info("Returning from View data")
                await page.go_back()
                await page.wait_for_selector("tr.arco-table-tr", timeout=15000)
                await page.wait_for_timeout(500)
            except Exception:
                pass
        return data_page_url

    async def _switch_to_approved_tab(self, page) -> bool:
        self.logger.info("Switching to Approved tab")
        for label in self.APPROVED_TAB_TEXTS:
            target = page.get_by_text(label, exact=False).first
            if await target.count():
                try:
                    await target.click()
                    self.logger.info("Approved tab selected", label=label)
                    await page.wait_for_timeout(1500)
                    return True
                except Exception:
                    continue
        self.logger.warning("Approved tab not found")
        return False

    async def _is_pagination_next_disabled(self, next_btn) -> bool:
        try:
            disabled_attr = await next_btn.get_attribute("aria-disabled")
            class_attr = (await next_btn.get_attribute("class")) or ""
            return disabled_attr == "true" or "disabled" in class_attr
        except Exception:
            return False

    async def _go_next_campaign_page(self, page) -> bool:
        next_btn = page.locator("li.arco-pagination-item-next").first
        if not await next_btn.count():
            self.logger.info("Campaign next page button not found")
            return False
        if await self._is_pagination_next_disabled(next_btn):
            self.logger.info("Campaign next page disabled")
            return False
        try:
            await next_btn.scroll_into_view_if_needed()
            await next_btn.click()
            await page.wait_for_timeout(1500)
        except Exception:
            self.logger.warning("Campaign next page click failed")
            return False
        return await self._wait_campaign_table(page) > 0

    async def _go_next_products_page(self, page) -> bool:
        next_btn = page.locator("li.arco-pagination-item-next").first
        if not await next_btn.count():
            self.logger.info("Products next page button not found")
            return False
        if await self._is_pagination_next_disabled(next_btn):
            self.logger.info("Products next page disabled")
            return False
        try:
            await next_btn.scroll_into_view_if_needed()
            await next_btn.click()
            await page.wait_for_timeout(1500)
        except Exception:
            self.logger.warning("Products next page click failed")
            return False
        return await self._wait_products_table(page) > 0

    async def _parse_products(
        self,
        page,
        campaign_meta: Dict[str, Any],
        detail_page_url: str,
        data_page_url: str,
    ) -> List[Dict[str, Any]]:
        all_results: List[Dict[str, Any]] = []
        page_index = 1

        while True:
            self.logger.info("Parsing products page", page=page_index)
            total_rows = await self._wait_products_table(page)
            if total_rows == 0:
                break

            rows = page.locator("tbody tr.arco-table-tr")
            if not await rows.count():
                rows = page.locator("table tbody tr")

            header_map: Dict[str, int] = {}
            try:
                ths = page.locator("thead tr th")
                th_count = await ths.count()
                for idx in range(th_count):
                    text = (await ths.nth(idx).inner_text()).strip()
                    if text:
                        header_map[text] = idx
            except Exception as exc:
                self.logger.warning("Header parse failed", error=str(exc), page_index=page_index)

            def get_col(*names: str, default: Optional[int] = None) -> Optional[int]:
                for name in names:
                    if name in header_map:
                        return header_map[name]
                return default

            idx_product = get_col("Product", "Product details", "Product Detail", default=1)
            idx_date = get_col("Date registered", "Registration date", default=2)
            idx_commission = get_col("Total commission rate", "Commission", default=3)
            idx_price = get_col("Sale Price", "Price", default=4)
            idx_stock = get_col("Stock", default=5)
            idx_available = get_col("Available sample", "Available samples", default=6)
            idx_items_sold = get_col("Items sold", "Sold", default=7)
            idx_shop = get_col("Shop info", default=8)

            row_count = await rows.count()
            self.logger.info("Products rows on page", page=page_index, count=row_count)
            for row_idx in range(row_count):
                row = rows.nth(row_idx)
                try:
                    tds = row.locator("td")
                    tds_count = await tds.count()
                    if tds_count == 0:
                        continue

                    product_name = ""
                    product_id = ""
                    image_link = ""
                    if idx_product is not None and idx_product < tds_count:
                        prod_td = tds.nth(idx_product)
                        name_node = prod_td.locator(
                            "div[class*='arco-typography'], div.text-ellipsis, a"
                        ).first
                        if await name_node.count():
                            title_text = await name_node.get_attribute("title")
                            if title_text and title_text.strip():
                                product_name = title_text.strip()
                            else:
                                product_name = (await name_node.inner_text()).strip()

                        prod_text = (await prod_td.inner_text()).strip()
                        match = re.search(r"ID\s*:?\s*(\d+)", prod_text)
                        if match:
                            product_id = match.group(1)

                        img = prod_td.locator("img").first
                        if await img.count():
                            image_link = (await img.get_attribute("src")) or ""

                    date_registered = ""
                    if idx_date is not None and idx_date < tds_count:
                        date_registered = (await tds.nth(idx_date).inner_text()).strip()

                    commission_rate = ""
                    if idx_commission is not None and idx_commission < tds_count:
                        raw_commission = (await tds.nth(idx_commission).inner_text()).strip()
                        lines = [line.strip() for line in raw_commission.splitlines() if line.strip()]
                        commission_rate = lines[0] if lines else raw_commission

                    sale_price_min = ""
                    sale_price_max = ""
                    if idx_price is not None and idx_price < tds_count:
                        raw_price = (await tds.nth(idx_price).inner_text()).strip()
                        nums = re.findall(r"[0-9]+(?:\.[0-9]+)?", raw_price)
                        if len(nums) >= 2:
                            sale_price_min, sale_price_max = nums[0], nums[1]
                        elif len(nums) == 1:
                            sale_price_min = nums[0]
                            sale_price_max = nums[0]

                    stock = ""
                    if idx_stock is not None and idx_stock < tds_count:
                        stock = (await tds.nth(idx_stock).inner_text()).strip()

                    available_stock = ""
                    if idx_available is not None and idx_available < tds_count:
                        available_stock = (await tds.nth(idx_available).inner_text()).strip()

                    product_rating = ""
                    rating_node = row.locator("div.text-neutral-text1.text-body-m-regular").first
                    if await rating_node.count():
                        product_rating = (await rating_node.inner_text()).strip()

                    reviews_count = ""
                    review_node = row.locator("div.text-neutral-text3.text-body-s-regular").first
                    if await review_node.count():
                        raw = (await review_node.inner_text()).strip()
                        reviews_count = raw.replace("reviews", "").replace("review", "").strip()

                    items_sold = ""
                    if idx_items_sold is not None and idx_items_sold < tds_count:
                        items_sold = (await tds.nth(idx_items_sold).inner_text()).strip()

                    shop_name = ""
                    shop_phone = ""
                    if idx_shop is not None and idx_shop < tds_count:
                        raw_shop = (await tds.nth(idx_shop).inner_text()).strip()
                        lines = [line.strip() for line in raw_shop.splitlines() if line.strip()]
                        if lines:
                            shop_name = lines[0]
                        for line in lines[1:]:
                            if "+" in line:
                                shop_phone = line

                    shop_code = ""
                    shop_code_node = row.locator("div.shop_code span.text-body-s-regular").first
                    if await shop_code_node.count():
                        raw_text = (await shop_code_node.inner_text()).strip()
                        if ":" in raw_text:
                            shop_code = raw_text.split(":", 1)[1].strip()
                        else:
                            shop_code = raw_text

                    row_data = {
                        **campaign_meta,
                        "product_id": product_id,
                        "product_name": product_name,
                        "date_registered": date_registered,
                        "commission_rate": commission_rate,
                        "sale_price_min": sale_price_min,
                        "sale_price_max": sale_price_max,
                        "stock": stock,
                        "available_sample": available_stock,
                        "product_rating": product_rating,
                        "items_sold": items_sold,
                        "reviews_count": reviews_count,
                        "shop_name": shop_name,
                        "shop_phone": shop_phone,
                        "shop_code": shop_code,
                        "data_page_url": data_page_url,
                        "detail_page_url": detail_page_url,
                        "crawl_timestamp": datetime.now().isoformat(timespec="seconds"),
                        "image_link": image_link,
                    }
                    all_results.append(row_data)
                except Exception as exc:
                    self.logger.warning(
                        "Product row parse failed",
                        error=str(exc),
                        page_index=page_index,
                        row_index=row_idx,
                    )

            if not await self._go_next_products_page(page):
                self.logger.info("No more product pages", page=page_index)
                break
            page_index += 1

        return all_results

    def _build_export_path(self, options: CampaignCrawlOptions) -> Path:
        campaign_fragment = "all"
        if options.campaign_ids:
            if len(options.campaign_ids) == 1:
                campaign_fragment = options.campaign_ids[0]
            else:
                campaign_fragment = f"{options.campaign_ids[0]}_plus_{len(options.campaign_ids) - 1}"
        safe_campaign = re.sub(r"[^0-9A-Za-z]+", "_", campaign_fragment).strip("_") or "all"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_stem = f"campaign_products_{options.region.lower()}_{safe_campaign}_{timestamp}"
        return self.export_dir / f"{file_stem}.xlsx"

    def _ensure_export_path(self, options: CampaignCrawlOptions) -> Path:
        if not self._export_path:
            self.export_dir.mkdir(parents=True, exist_ok=True)
            self._export_path = self._build_export_path(options)
        return self._export_path

    def _append_rows(self, rows: List[Dict[str, Any]], options: CampaignCrawlOptions) -> Optional[str]:
        if not rows:
            return None

        export_path = self._ensure_export_path(options)
        df_new = pd.DataFrame(rows, columns=self.EXPORT_COLUMNS)

        if export_path.suffix.lower() == ".csv":
            write_header = not export_path.exists()
            df_new.to_csv(
                export_path,
                mode="a",
                header=write_header,
                index=False,
                encoding="utf-8-sig",
            )
            return str(export_path)

        if not export_path.exists():
            df_new.to_excel(export_path, index=False)
            return str(export_path)

        try:
            existing = pd.read_excel(export_path)
            merged = pd.concat([existing, df_new], ignore_index=True)
            merged.to_excel(export_path, index=False)
            return str(export_path)
        except Exception as exc:
            csv_path = export_path.with_suffix(".csv")
            write_header = not csv_path.exists()
            df_new.to_csv(
                csv_path,
                mode="a",
                header=write_header,
                index=False,
                encoding="utf-8-sig",
            )
            self._export_path = csv_path
            self.logger.warning("Append to Excel failed; switched to CSV", error=str(exc), path=str(csv_path))
            return str(csv_path)

    def _export_rows(self, rows: List[Dict[str, Any]], options: CampaignCrawlOptions) -> Optional[str]:
        if not rows:
            return None
        export_path = self._ensure_export_path(options)
        df = pd.DataFrame(rows, columns=self.EXPORT_COLUMNS)
        try:
            df.to_excel(export_path, index=False)
            return str(export_path)
        except Exception as exc:
            csv_path = export_path.with_suffix(".csv")
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            self.logger.warning("Excel export failed, saved CSV", error=str(exc), path=str(csv_path))
            self._export_path = csv_path
            return str(csv_path)

    async def _crawl_campaigns(
        self,
        page,
        options: CampaignCrawlOptions,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not await self._navigate_to_my_campaign(page):
            raise PlaywrightError("Failed to navigate to My campaigns")

        if options.campaign_ids and len(options.campaign_ids) == 1 and not options.scan_all_pages:
            await self._apply_campaign_search(page, options.campaign_ids[0])

        rows: List[Dict[str, Any]] = []
        stats = {
            "campaign_pages": 0,
            "campaign_rows": 0,
            "campaigns_processed": 0,
            "products": 0,
        }
        remaining_ids = set(options.campaign_ids)
        page_index = 1

        while True:
            abort_page = False
            stats["campaign_pages"] += 1
            self.logger.info("Processing campaign page", page=page_index)
            base_row_count = await self._wait_campaign_table(page)
            if base_row_count == 0:
                break

            for row_index in range(base_row_count):
                self.logger.info("Processing campaign row", page=page_index, row=row_index + 1, total=base_row_count)
                current_rows = page.locator("tr.arco-table-tr")
                if await current_rows.count() == 0:
                    current_rows = page.locator("table tbody tr")
                if await current_rows.count() <= row_index:
                    continue
                row = current_rows.nth(row_index)
                campaign_meta = await self._parse_campaign_row(row)
                if not campaign_meta:
                    continue
                stats["campaign_rows"] += 1

                campaign_id = campaign_meta.get("campaign_id") or ""
                if campaign_id:
                    self.logger.info("Campaign found", campaign_id=campaign_id)
                if remaining_ids and campaign_id not in remaining_ids:
                    continue

                detail_btn, data_btn = await self._find_view_buttons(row)

                data_page_url = ""
                if data_btn:
                    data_page_url = await self._capture_view_data(page, data_btn)
                    current_rows = page.locator("tr.arco-table-tr")
                    if await current_rows.count() == 0:
                        current_rows = page.locator("table tbody tr")
                    if await current_rows.count() <= row_index:
                        continue
                    row = current_rows.nth(row_index)
                    detail_btn, _ = await self._find_view_buttons(row)

                if not detail_btn:
                    self.logger.warning("View details button missing", campaign_id=campaign_id or None)
                    continue

                try:
                    await detail_btn.click()
                except Exception:
                    self.logger.warning("View details click failed", campaign_id=campaign_id or None)
                    continue

                await page.wait_for_timeout(2000)
                detail_page_url = page.url
                self.logger.info("Campaign detail opened", url=detail_page_url)

                if not await self._switch_to_approved_tab(page):
                    try:
                        await page.go_back()
                        await page.wait_for_selector("tr.arco-table-tr", timeout=15000)
                    except Exception:
                        pass
                    continue

                products = await self._parse_products(
                    page,
                    campaign_meta,
                    detail_page_url,
                    data_page_url,
                )
                self.logger.info("Products parsed", campaign_id=campaign_id or None, count=len(products))
                try:
                    await self._ingest_campaign_products(campaign_meta, products, options)
                    self.logger.info(
                        "Ingestion completed",
                        campaign_id=campaign_id or None,
                        products=len(products),
                    )
                except MessageProcessingError:
                    raise
                except Exception as exc:
                    self.logger.error(
                        "Ingestion failed",
                        campaign_id=campaign_id or None,
                        error=str(exc),
                        exc_info=True,
                    )
                    raise
                rows.extend(products)
                stats["campaigns_processed"] += 1
                stats["products"] += len(products)
                if options.export_excel:
                    export_path = self._append_rows(products, options)
                    if export_path:
                        self.logger.info(
                            "Appended campaign rows",
                            campaign_id=campaign_id or None,
                            count=len(products),
                            path=export_path,
                        )

                if remaining_ids and campaign_id in remaining_ids:
                    remaining_ids.discard(campaign_id)

                try:
                    self.logger.info("Returning to campaign list", campaign_id=campaign_id or None)
                    await page.go_back()
                    await page.wait_for_selector("tr.arco-table-tr", timeout=15000)
                    await page.wait_for_timeout(500)
                except Exception:
                    abort_page = True
                    break

            if abort_page:
                break

            if options.max_pages and page_index >= options.max_pages:
                self.logger.info("Reached max campaign pages", max_pages=options.max_pages)
                break
            if options.campaign_ids and not options.scan_all_pages and not remaining_ids:
                self.logger.info("Target campaign ids completed")
                break
            if not await self._go_next_campaign_page(page):
                self.logger.info("No more campaign pages")
                break

            page_index += 1

        return rows, stats

    async def run(self) -> Dict[str, Any]:
        return await self.run_from_payload({})

    async def run_from_payload(self, body: Dict[str, Any]) -> Dict[str, Any]:
        options = self._parse_options(body or {})
        self._resolve_account(options)
        options.region = self.default_region
        await self.initialize()
        if not self._page:
            raise PlaywrightError("Playwright page not initialized")
        if not await self.login(self._page):
            raise PlaywrightError("Login failed")
        await self._wait_for_home_ready(self._page)

        rows, stats = await self._crawl_campaigns(self._page, options)

        export_path = None
        if options.export_excel:
            export_path = self._export_rows(rows, options)
            if export_path:
                self.logger.info("Campaign export completed", path=export_path, rows=len(rows))

        return {
            "login": "ok",
            "rows": len(rows),
            "export_path": export_path,
            "stats": stats,
        }

    async def close(self) -> None:
        try:
            await self.ingestion_client.aclose()
        except Exception:
            self.logger.warning("Failed to close ingestion client", exc_info=True)
        await _close_with_timeout(self._page, "page")
        await _close_with_timeout(self._context, "context")
        await _close_with_timeout(self._browser, "browser")
        await _close_with_timeout(self._playwright, "playwright")
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
