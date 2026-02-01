from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from aio_pika import ExchangeType

from common.core.config import get_settings
from common.core.exceptions import PlaywrightError
from common.core.logger import get_logger
from common.playwright.shop_login_manager import ShopLoginManager
from common.mq.connection import RabbitMQConnection
from common.mq.producer_base import ProducerBase
from apps.portal_tiktok_sample_crawler.services.email_verifier import GmailVerificationCode
from apps.portal_tiktok_creator_crawler.services.creator_ingestion_client import CreatorIngestionClient

PREFERRED_UUID_NODE = 0x2AA7A70856D4

from .shop_outreach_models import AccountProfile, ShopOutreachOptions


class ShopOutreachChatbotProducer(ProducerBase):
    """MQ publisher for shop outreach chatbot tasks."""


class ShopOutreachCrawlerService:
    """Shop-end creator connection crawler (MQ-triggered, no DB ingest)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = get_logger().bind(service="portal_tiktok_shop_creator_crawler")
        self.default_region = str(getattr(self.settings, "SHOP_OUTREACH_DEFAULT_REGION", "MX") or "MX").upper()
        self.account_config_path = Path(
            getattr(self.settings, "SHOP_OUTREACH_ACCOUNT_CONFIG_PATH", "configs/accounts.json")
        )
        self.accounts_data = self._load_accounts_config()

        self.login_manager = ShopLoginManager(
            login_url=self._login_url(self.default_region),
            manual_login_default=bool(getattr(self.settings, "SHOP_OUTREACH_MANUAL_LOGIN", False)),
            manual_login_timeout_ms=int(
                getattr(self.settings, "SHOP_OUTREACH_MANUAL_LOGIN_TIMEOUT_SECONDS", 300) or 300
            )
            * 1000,
            manual_email_code_input=bool(
                getattr(self.settings, "SHOP_OUTREACH_MANUAL_EMAIL_CODE_INPUT", True)
            ),
            manual_email_code_input_timeout_seconds=int(
                getattr(self.settings, "SHOP_OUTREACH_MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS", 180)
            ),
            manual_email_code_only=bool(
                getattr(self.settings, "SHOP_OUTREACH_MANUAL_EMAIL_CODE_INPUT", True)
            ),
        )

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self.account_profile: Optional[AccountProfile] = None
        self.gmail_verifier: Optional[GmailVerificationCode] = None
        self.processed_creators: Set[str] = set()
        self._export_path: Optional[str] = None
        self._creator_scroll_selector: Optional[str] = None
        self._chatbot_publisher_conn: Optional[RabbitMQConnection] = None
        self._chatbot_publisher: Optional[ShopOutreachChatbotProducer] = None
        self.source = "portal_tiktok_shop_creator_crawler"

        inner_api_token = getattr(self.settings, "INNER_API_AUTH_TOKEN", None)
        if not inner_api_token:
            valid_tokens = getattr(self.settings, "INNER_API_AUTH_VALID_TOKENS", []) or []
            inner_api_token = valid_tokens[0] if valid_tokens else None
        self.ingestion_client = CreatorIngestionClient(
            base_url=self.settings.INNER_API_BASE_URL,
            creator_path=self.settings.INNER_API_CREATOR_PATH,
            header_name=self.settings.INNER_API_AUTH_REQUIRED_HEADER,
            token=inner_api_token,
            timeout=float(self.settings.INNER_API_TIMEOUT),
        )

    def _login_url(self, region: str) -> str:
        override = str(getattr(self.settings, "SHOP_OUTREACH_LOGIN_URL", "") or "").strip()
        if override:
            return override
        return "https://seller-mx.tiktok.com/account/login"

    def _target_url(self, region: str) -> str:
        override = str(getattr(self.settings, "SHOP_OUTREACH_TARGET_URL", "") or "").strip()
        if override:
            region_key = (region or self.default_region or "MX").upper()
            if "{region}" in override:
                return override.format(region=region_key)
            if "shop_region=" in override:
                return re.sub(r"shop_region=[A-Za-z]+", f"shop_region={region_key}", override)
            return override
        region_key = (region or self.default_region or "MX").upper()
        return f"https://affiliate.tiktok.com/connection/creator?shop_region={region_key}"

    def _load_accounts_config(self) -> List[Dict[str, Any]]:
        if not self.account_config_path.exists():
            return []
        try:
            with self.account_config_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            accounts = data.get("accounts", [])
            return accounts if isinstance(accounts, list) else []
        except Exception as exc:
            self.logger.warning("Failed to load accounts config", path=str(self.account_config_path), error=str(exc))
            return []

    def _persist_accounts_config(self) -> None:
        if not self.account_config_path:
            return
        try:
            payload = {"accounts": self.accounts_data}
            with self.account_config_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.logger.warning("Failed to persist accounts config", error=str(exc))

    def _ensure_account_creator_id(self, account: Dict[str, Any]) -> str:
        creator_id = str(account.get("creator_id") or account.get("creatorId") or "").strip()
        if creator_id:
            return creator_id
        creator_id = str(uuid.uuid1(node=PREFERRED_UUID_NODE)).upper()
        account["creator_id"] = creator_id
        self._persist_accounts_config()
        self.logger.info("Generated creator_id for account", account_name=account.get("name"), creator_id=creator_id)
        return creator_id

    def _select_account(self, region: Optional[str], account_name: Optional[str]) -> AccountProfile:
        desired_region = (region or self.default_region or "MX").upper()
        if account_name:
            for account in self.accounts_data:
                if account_name.lower() == str(account.get("name", "")).lower():
                    enabled = account.get("enabled", True)
                    if not enabled:
                        raise PlaywrightError(f"Account {account_name} is disabled")
                    creator_id = self._ensure_account_creator_id(account)
                    return AccountProfile(
                        name=account.get("name", ""),
                        login_email=account.get("login_email", ""),
                        login_password=account.get("login_password"),
                        gmail_username=account.get("gmail_username", ""),
                        gmail_app_password=account.get("gmail_app_password", ""),
                        region=str(account.get("region", desired_region)).upper(),
                        creator_id=creator_id,
                        enabled=enabled,
                    )
            raise PlaywrightError(f"Account {account_name} not found in config")

        default_email = str(getattr(self.settings, "SHOP_OUTREACH_LOGIN_EMAIL", "") or "").strip()
        if default_email:
            return AccountProfile(
                name="DEFAULT",
                login_email=default_email,
                login_password=getattr(self.settings, "SHOP_OUTREACH_LOGIN_PASSWORD", None),
                gmail_username=str(getattr(self.settings, "SHOP_OUTREACH_GMAIL_USERNAME", "") or ""),
                gmail_app_password=str(getattr(self.settings, "SHOP_OUTREACH_GMAIL_APP_PASSWORD", "") or ""),
                region=desired_region,
                creator_id=None,
                enabled=True,
            )

        for account in self.accounts_data:
            account_region = str(account.get("region", "")).upper()
            enabled = account.get("enabled", True)
            if enabled and account_region == desired_region:
                creator_id = self._ensure_account_creator_id(account)
                return AccountProfile(
                    name=account.get("name", ""),
                    login_email=account.get("login_email", ""),
                    login_password=account.get("login_password"),
                    gmail_username=account.get("gmail_username", ""),
                    gmail_app_password=account.get("gmail_app_password", ""),
                    region=account_region,
                    creator_id=creator_id,
                    enabled=enabled,
                )

        return AccountProfile(
            name="DEFAULT",
            login_email=str(getattr(self.settings, "SHOP_OUTREACH_LOGIN_EMAIL", "") or ""),
            login_password=getattr(self.settings, "SHOP_OUTREACH_LOGIN_PASSWORD", None),
            gmail_username=str(getattr(self.settings, "SHOP_OUTREACH_GMAIL_USERNAME", "") or ""),
            gmail_app_password=str(getattr(self.settings, "SHOP_OUTREACH_GMAIL_APP_PASSWORD", "") or ""),
            region=desired_region,
            creator_id=None,
            enabled=True,
        )

    @staticmethod
    def _normalize_messages(value: Any) -> Optional[List[Dict[str, Any]]]:
        if not value:
            return None
        if isinstance(value, dict):
            value = [value]
        if isinstance(value, list):
            normalized: List[Dict[str, Any]] = []
            for item in value:
                if isinstance(item, str):
                    normalized.append({"type": "text", "content": item})
                    continue
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if content is None:
                    continue
                normalized.append(
                    {
                        "type": str(item.get("type") or "text"),
                        "content": content,
                        "meta": item.get("meta"),
                    }
                )
            return normalized or None
        return None

    def _parse_options(self, body: Dict[str, Any]) -> ShopOutreachOptions:
        region = str(body.get("region") or body.get("shopRegion") or self.default_region).upper()
        account_name = body.get("accountName") or body.get("account_name")
        headless = body.get("headless")
        manual_login = body.get("manualLogin")
        manual_code = body.get("manualEmailCodeInput")
        task_id = body.get("taskId") or body.get("task_id")
        operator_id = body.get("operatorId") or body.get("operator_id")
        brand_name = body.get("brandName") or body.get("brand_name")
        max_creators = body.get("maxCreators") or getattr(self.settings, "SHOP_OUTREACH_MAX_CREATORS", 30)
        try:
            max_creators = int(max_creators)
        except Exception:
            max_creators = 30

        search_strategy = body.get("searchStrategy") or {}
        if isinstance(search_strategy, str):
            try:
                search_strategy = json.loads(search_strategy)
            except Exception:
                search_strategy = {}

        strategy_json = getattr(self.settings, "SHOP_OUTREACH_SEARCH_STRATEGY_JSON", None)
        if strategy_json:
            try:
                parsed = json.loads(strategy_json)
                if isinstance(parsed, dict):
                    merged = dict(parsed)
                    if isinstance(search_strategy, dict):
                        merged.update(search_strategy)
                    search_strategy = merged
            except Exception as exc:
                self.logger.warning("Failed to parse search strategy JSON", error=str(exc))

        messages_value = body.get("messages") or body.get("messageTemplates") or body.get("message")
        if not messages_value:
            messages_json = getattr(self.settings, "SHOP_OUTREACH_CHATBOT_MESSAGES_JSON", None)
            if messages_json:
                try:
                    messages_value = json.loads(messages_json)
                except Exception as exc:
                    self.logger.warning("Failed to parse default messages JSON", error=str(exc))
        messages = self._normalize_messages(messages_value)

        export_enabled = bool(getattr(self.settings, "SHOP_OUTREACH_ENABLE_EXPORT", False))
        export_dir = str(getattr(self.settings, "SHOP_OUTREACH_EXPORT_DIR", "data/shop_outreach") or "data/shop_outreach")

        return ShopOutreachOptions(
            region=region,
            account_name=account_name,
            headless=headless,
            manual_login=manual_login,
            manual_email_code_input=manual_code,
            max_creators=max_creators,
            search_strategy=search_strategy if isinstance(search_strategy, dict) else {},
            export_enabled=export_enabled,
            export_dir=export_dir,
            messages=messages,
            task_id=str(task_id).strip() if task_id else None,
            operator_id=str(operator_id).strip() if operator_id else None,
            brand_name=str(brand_name).strip() if brand_name else None,
        )

    def _sync_login_manager(self, options: ShopOutreachOptions) -> None:
        self.login_manager.login_url = self._login_url(options.region)
        if options.manual_login is not None:
            self.login_manager.manual_login_default = bool(options.manual_login)
        if options.manual_email_code_input is not None:
            self.login_manager.manual_email_code_input = bool(options.manual_email_code_input)
            self.login_manager.manual_email_code_only = bool(options.manual_email_code_input)

    def _resolve_operator_id(self, options: ShopOutreachOptions) -> str:
        if options.operator_id:
            return options.operator_id
        if self.account_profile and self.account_profile.creator_id:
            options.operator_id = self.account_profile.creator_id
            return options.operator_id
        options.operator_id = str(uuid.uuid1(node=PREFERRED_UUID_NODE)).upper()
        return options.operator_id

    async def initialize(self, options: ShopOutreachOptions) -> None:
        if self._playwright:
            return
        headless = (
            options.headless
            if options.headless is not None
            else bool(getattr(self.settings, "PLAYWRIGHT_HEADLESS", False))
        )
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(45_000)
        self.logger.info("Playwright session initialized", headless=headless)

    async def _ensure_chatbot_publisher(self) -> None:
        if self._chatbot_publisher:
            return
        if not bool(getattr(self.settings, "SHOP_OUTREACH_CHATBOT_PUBLISH_ENABLED", True)):
            return
        exchange_name = str(
            getattr(self.settings, "SHOP_OUTREACH_CHATBOT_EXCHANGE_NAME", "chatbot.topic") or "chatbot.topic"
        )
        routing_key = str(
            getattr(self.settings, "SHOP_OUTREACH_CHATBOT_ROUTING_KEY", "chatbot.shop_outreach.*")
            or "chatbot.shop_outreach.*"
        )
        queue_name = str(
            getattr(self.settings, "SHOP_OUTREACH_CHATBOT_QUEUE_NAME", "chatbot.shop_outreach.queue.topic")
            or "chatbot.shop_outreach.queue.topic"
        )
        amqp_url = (
            f"amqp://{quote_plus(self.settings.RABBITMQ_USERNAME)}:"
            f"{quote_plus(self.settings.RABBITMQ_PASSWORD)}@"
            f"{self.settings.RABBITMQ_HOST}:{self.settings.RABBITMQ_PORT}/"
            f"{quote_plus(self.settings.RABBITMQ_VHOST)}"
        )
        self._chatbot_publisher_conn = RabbitMQConnection(
            url=amqp_url,
            exchange_name=exchange_name,
            routing_key=routing_key,
            queue_name=queue_name,
            prefetch_count=1,
            reconnect_delay=getattr(self.settings, "RABBITMQ_RECONNECT_DELAY", 5),
            max_reconnect_attempts=getattr(self.settings, "RABBITMQ_MAX_RECONNECT_ATTEMPTS", 5),
            at_most_once=False,
            exchange_type=ExchangeType.TOPIC,
        )
        self._chatbot_publisher = ShopOutreachChatbotProducer(self._chatbot_publisher_conn)

    async def close(self) -> None:
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._browser = None
        self._playwright = None
        self._page = None
        if self._chatbot_publisher_conn:
            try:
                await self._chatbot_publisher_conn.close()
            except Exception:
                pass
        self._chatbot_publisher_conn = None
        self._chatbot_publisher = None
        if self.ingestion_client:
            try:
                await self.ingestion_client.aclose()
            except Exception:
                pass

    async def _dump_debug(self, page, tag: str) -> None:
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = Path("logs")
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"shop_creator_{tag}_{ts}.png"
            await page.screenshot(path=str(path), full_page=True)
            self.logger.info("Saved debug screenshot", path=str(path))
        except Exception:
            pass

    async def login(self, page, options: ShopOutreachOptions) -> None:
        self._sync_login_manager(options)
        self.account_profile = self._select_account(options.region, options.account_name)
        if not self.account_profile.login_email and not self.login_manager.manual_login_default:
            raise PlaywrightError("Missing login email; enable manual login or configure account")

        if self.account_profile.gmail_username and self.account_profile.gmail_app_password:
            self.gmail_verifier = GmailVerificationCode(
                username=self.account_profile.gmail_username,
                app_password=self.account_profile.gmail_app_password,
            )
        else:
            self.gmail_verifier = None

        await self.login_manager.perform_login(
            page,
            self.account_profile,
            self.gmail_verifier,
            dump_debug_cb=self._dump_debug,
        )

    async def navigate_to_creator_connection(self, page, region: str) -> bool:
        target_url = self._target_url(region)
        self.logger.info("Navigating to creator connection", url=target_url)
        await page.goto(target_url, wait_until="domcontentloaded")
        for selector in ('text="Find creators"', 'text="Creators"', 'text="Creator"'):
            try:
                await page.wait_for_selector(selector, timeout=30_000)
                return True
            except Exception:
                continue
        return False

    async def apply_search_strategy(self, page, strategy: Dict[str, Any]) -> None:
        if not strategy:
            return
        keyword = str(strategy.get("search_keywords") or strategy.get("keyword") or "").strip()
        if keyword:
            selectors = [
                'input[placeholder*="Search"]',
                'input[placeholder*="Creator"]',
                'input[data-tid="m4b_input_search"]',
            ]
            for selector in selectors:
                loc = page.locator(selector).first
                if await loc.count():
                    await loc.fill("")
                    await loc.fill(keyword)
                    await loc.press("Enter")
                    await page.wait_for_timeout(2000)
                    self.logger.info("Applied search keyword", keyword=keyword)
                    break

    async def get_creators_in_current_page(self, page) -> List[str]:
        creators = await page.evaluate(
            """
            () => {
                const creators = [];
                const selectors = [
                    'span[data-e2e="fbc99397-6043-1b37"]',
                    'span.text-body-m-medium.text-neutral-text1',
                    'div[class*="creator-card"] span',
                    'a[href*="creator/detail"] span',
                    'a[href*="connection/creator/detail"] span',
                ];
                for (const selector of selectors) {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => {
                        const text = el.textContent?.trim();
                        if (text && text.length > 0 && !creators.includes(text)) {
                            creators.push(text);
                        }
                    });
                }
                return creators;
            }
            """
        )
        if not isinstance(creators, list):
            return []
        return [str(item).strip() for item in creators if str(item).strip()]

    async def _wait_for_creators(self, page, timeout_ms: int = 30000) -> List[str]:
        deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000.0)
        while asyncio.get_event_loop().time() < deadline:
            creators = await self.get_creators_in_current_page(page)
            if creators:
                return creators
            await page.wait_for_timeout(1000)
        return []

    async def _safe_click(self, locator, timeout: int = 2000) -> bool:
        try:
            await locator.scroll_into_view_if_needed()
            await locator.click(timeout=timeout)
            return True
        except Exception:
            try:
                await locator.click(timeout=timeout, force=True)
                return True
            except Exception:
                return False

    async def _wait_for_detail_ready(self, page, timeout_ms: int = 6000) -> bool:
        markers = [
            "#creator-detail-profile-container",
            'button:has-text("Message")',
            'text="Message"',
            'text="Send message"',
            'text="Chat"',
        ]
        for selector in markers:
            try:
                await page.wait_for_selector(selector, timeout=timeout_ms)
                return True
            except Exception:
                continue
        return False

    async def _find_message_button(self, page, timeout_ms: int = 8000):
        selectors = [
            'button:has(svg.alliance-icon.alliance-icon-Message)',
            'div[role="button"]:has(svg.alliance-icon.alliance-icon-Message)',
            'button:has-text("Message")',
            'button:has-text("Send message")',
            'button:has-text("Chat")',
            'div[role="button"]:has-text("Message")',
        ]
        deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000.0)
        while asyncio.get_event_loop().time() < deadline:
            for frame in page.frames:
                for selector in selectors:
                    try:
                        locator = frame.locator(selector).first
                        if await locator.count():
                            return locator
                    except Exception:
                        continue
            await page.wait_for_timeout(500)
        return None

    async def _open_creator_detail(self, page, creator_name: str):
        selectors = [
            f'div[class*="creator-card"]:has(span:has-text("{creator_name}"))',
            f'div[class*="item"]:has(span:has-text("{creator_name}"))',
            f'a:has(span:has-text("{creator_name}"))',
            f'span:has-text("{creator_name}")',
        ]
        locator = None
        for selector in selectors:
            candidate = page.locator(selector).first
            if await candidate.count():
                locator = candidate
                break
        if not locator:
            self.logger.warning("Creator card not found", creator_name=creator_name)
            return None

        try:
            async with page.context.expect_page(timeout=8000) as popup_info:
                await self._safe_click(locator)
            detail_page = await popup_info.value
            self.logger.info("Creator detail opened in new page", creator_name=creator_name, url=detail_page.url)
            return detail_page
        except Exception:
            await self._safe_click(locator)
            if await self._wait_for_detail_ready(page, timeout_ms=6000):
                self.logger.info("Creator detail opened in same page", creator_name=creator_name, url=page.url)
                return page
            self.logger.warning("Creator detail did not open", creator_name=creator_name)
            return None

    async def _open_chat_page(self, detail_page) -> Optional[Any]:
        message_btn = await self._find_message_button(detail_page)
        if not message_btn:
            self.logger.warning("Message button not found", url=detail_page.url)
            return None

        try:
            async with detail_page.context.expect_page(timeout=5000) as popup_info:
                await self._safe_click(message_btn)
            chat_page = await popup_info.value
            self.logger.info("Chat page opened in new page", url=chat_page.url)
            return chat_page
        except Exception:
            await self._safe_click(message_btn)
            await detail_page.wait_for_timeout(1500)
            if await detail_page.locator('div[class*="message"], div[class*="chat"], div[class*="conversation"]').count():
                self.logger.info("Chat opened in same page", url=detail_page.url)
                return detail_page
            self.logger.warning("Chat page did not open after clicking message", url=detail_page.url)
            return None

    def _extract_creator_id_from_url(self, url: str) -> str:
        for pattern in (r"[?&]cid=(\d+)", r"[?&]creator_id=(\d+)", r"[?&]creatorId=(\d+)"):
            match = re.search(pattern, url or "")
            if match:
                return match.group(1)
        return ""

    def _extract_region_from_url(self, url: str) -> Optional[str]:
        match = re.search(r"[?&]shop_region=([A-Za-z]+)", url or "")
        if match:
            return match.group(1).upper()
        return None

    async def _extract_shop_id(self, page) -> str:
        try:
            shop_id = await page.evaluate(
                """
                () => {
                    const attrSelectors = ['[data-shop-id]', '[data-shopid]', '[data-shopId]'];
                    for (const sel of attrSelectors) {
                        const el = document.querySelector(sel);
                        if (!el) continue;
                        const val = el.getAttribute('data-shop-id')
                            || el.getAttribute('data-shopid')
                            || el.getAttribute('data-shopId');
                        if (val) return val;
                    }
                    const scripts = Array.from(document.scripts || []);
                    for (const script of scripts) {
                        const text = script.textContent || '';
                        let m = text.match(/"shop_id"\\s*:\\s*"?(\\d{6,})"?/);
                        if (m) return m[1];
                        m = text.match(/"shopId"\\s*:\\s*"?(\\d{6,})"?/);
                        if (m) return m[1];
                    }
                    const winKeys = ['__INITIAL_STATE__', '__INITIAL_DATA__', '__APP_STATE__', '__NUXT__'];
                    for (const key of winKeys) {
                        try {
                            const data = window[key];
                            if (!data) continue;
                            const text = JSON.stringify(data);
                            let m = text.match(/"shop_id"\\s*:\\s*"?(\\d{6,})"?/);
                            if (m) return m[1];
                            m = text.match(/"shopId"\\s*:\\s*"?(\\d{6,})"?/);
                            if (m) return m[1];
                        } catch (e) {}
                    }
                    return "";
                }
                """
            )
            return str(shop_id or "").strip()
        except Exception:
            return ""

    def _build_chat_url(self, shop_id: str, creator_id: str, region: Optional[str]) -> Optional[str]:
        shop_id = str(shop_id or "").strip()
        creator_id = str(creator_id or "").strip()
        if not shop_id or not creator_id:
            return None
        region_key = (region or self.default_region or "MX").upper()
        return (
            "https://affiliate.tiktok.com/seller/im"
            f"?shop_id={shop_id}&creator_id={creator_id}"
            f"&enter_from=affiliate_creator_details&shop_region={region_key}"
        )

    @staticmethod
    def _normalize_label(label: str) -> str:
        return re.sub(r"\\s+", " ", label.strip().lower())

    @staticmethod
    def _percent_to_decimal(value: Optional[str]) -> Optional[float]:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        cleaned = raw.replace("%", "").replace(",", "").strip()
        try:
            number = float(cleaned)
        except Exception:
            return None
        if "%" in raw or number > 1:
            return number / 100.0
        return number

    async def _extract_metric_cards(self, page) -> Dict[str, str]:
        try:
            data = await page.evaluate(
                """
                () => {
                    const results = {};
                    const cards = Array.from(document.querySelectorAll('div[data-e2e="f6855061-9011-24ab"]'));
                    for (const card of cards) {
                        const labelNode = card.querySelector('[data-e2e="61148565-2ea3-4c1b"]')
                            || card.querySelector('span.text-body-l-regular');
                        const valueNode = card.querySelector('[data-e2e="0bc7b49d-b8b3-02d5"]')
                            || card.querySelector('span.text-head-l');
                        const label = labelNode ? labelNode.textContent.trim() : "";
                        const value = valueNode ? valueNode.textContent.trim() : "";
                        if (label && value) {
                            results[label] = value;
                        }
                    }
                    return results;
                }
                """
            )
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            return {}
        return {}

    async def _click_metric_arrows(self, page) -> int:
        clicked = 0
        arrows = page.locator('div[data-e2e="7a7839d9-8fa5-dd75"]')
        count = await arrows.count()
        for idx in range(count):
            loc = arrows.nth(idx)
            try:
                if not await loc.is_visible():
                    continue
            except Exception:
                continue
            if await self._safe_click(loc):
                clicked += 1
                await page.wait_for_timeout(400)
        return clicked

    async def _collect_metric_values(self, page) -> Dict[str, str]:
        metrics: Dict[str, str] = {}
        last_count = 0
        for _ in range(4):
            current = await self._extract_metric_cards(page)
            metrics.update(current)
            clicked = await self._click_metric_arrows(page)
            if len(metrics) == last_count or clicked == 0:
                break
            last_count = len(metrics)
            await page.wait_for_timeout(500)
        return metrics

    async def _extract_chart_legends(self, page) -> Dict[str, List[Tuple[str, str]]]:
        try:
            data = await page.evaluate(
                """
                () => {
                    const output = {};
                    const containers = Array.from(document.querySelectorAll('.pcm-pc-container'));
                    for (const container of containers) {
                        const titleNode = container.querySelector('.pcm-pc-title');
                        const rawTitle = titleNode ? titleNode.textContent : '';
                        const title = rawTitle.replace(/\\s+/g, ' ').trim();
                        if (!title) continue;
                        const labels = Array.from(container.querySelectorAll('.pcm-pc-legend-label .ecom-data-overflow-text-content'))
                            .map(el => el.textContent.trim())
                            .filter(Boolean);
                        const values = Array.from(container.querySelectorAll('.pcm-pc-legend-value .ecom-data-overflow-text-content'))
                            .map(el => el.textContent.trim())
                            .filter(Boolean);
                        const pairs = [];
                        const count = Math.min(labels.length, values.length);
                        for (let i = 0; i < count; i += 1) {
                            pairs.push([labels[i], values[i]]);
                        }
                        output[title] = pairs;
                    }
                    return output;
                }
                """
            )
            if isinstance(data, dict):
                normalized: Dict[str, List[Tuple[str, str]]] = {}
                for key, pairs in data.items():
                    if not isinstance(pairs, list):
                        continue
                    cleaned_pairs: List[Tuple[str, str]] = []
                    for pair in pairs:
                        if (
                            isinstance(pair, list)
                            and len(pair) == 2
                            and str(pair[0]).strip()
                            and str(pair[1]).strip()
                        ):
                            cleaned_pairs.append((str(pair[0]).strip(), str(pair[1]).strip()))
                    if cleaned_pairs:
                        normalized[str(key).strip()] = cleaned_pairs
                return normalized
        except Exception:
            return {}
        return {}

    @staticmethod
    def _pairs_to_string(pairs: List[Tuple[str, str]]) -> Optional[str]:
        if not pairs:
            return None
        combined = [f"{label} | {value}" for label, value in pairs if label and value]
        return ", ".join(combined) if combined else None

    async def _extract_contact_info(self, page) -> Tuple[Optional[str], Optional[str]]:
        selectors = [
            '#creator-detail-profile-container svg.alliance-icon-Phone',
            '#creator-detail-profile-container svg.alliance-icon-Email',
            'svg.alliance-icon-Phone',
            'svg.alliance-icon-Email',
        ]
        for selector in selectors:
            locator = page.locator(selector).first
            if await locator.count():
                await self._safe_click(locator)
                await page.wait_for_timeout(800)
                break

        contact_data = await page.evaluate(
            """
            () => {
                const findValue = (keyword) => {
                    const lowerKeyword = keyword.toLowerCase();
                    const nodes = Array.from(document.querySelectorAll('div, span'));
                    for (const node of nodes) {
                        const text = (node.textContent || '').trim();
                        if (!text) continue;
                        if (!text.toLowerCase().includes(lowerKeyword)) continue;
                        if (text.includes(':')) {
                            const parts = text.split(':');
                            const value = parts.slice(1).join(':').trim();
                            if (value) return value;
                        }
                        const parent = node.parentElement;
                        if (parent) {
                            const valueNode = parent.querySelector('.arco-typography') || parent.querySelector('div:last-child');
                            const value = valueNode ? valueNode.textContent.trim() : '';
                            if (value && !value.toLowerCase().includes(lowerKeyword)) {
                                return value;
                            }
                        }
                    }
                    return '';
                };
                return {
                    whatsapp: findValue('whatsapp'),
                    email: findValue('email'),
                };
            }
            """
        )

        try:
            await self._safe_click(page.locator('span[data-e2e="b7f56c3b-f013-3448"]').first)
        except Exception:
            pass

        whatsapp = str(contact_data.get("whatsapp") or "").strip() if isinstance(contact_data, dict) else ""
        email = str(contact_data.get("email") or "").strip() if isinstance(contact_data, dict) else ""
        return (whatsapp or None, email or None)

    async def _extract_top_brands(self, page) -> Optional[str]:
        button = page.locator('button:has-text("View top brands")').first
        if not await button.count():
            return None
        if not await self._safe_click(button):
            return None
        await page.wait_for_timeout(800)
        brands = await page.evaluate(
            """
            () => {
                const items = Array.from(document.querySelectorAll('[data-e2e="710cdc7a-878f-599e"]'));
                return items.map(item => item.textContent.trim()).filter(Boolean);
            }
            """
        )
        try:
            await self._safe_click(page.locator('span[data-e2e="b7f56c3b-f013-3448"]').first)
        except Exception:
            pass
        if isinstance(brands, list) and brands:
            return ", ".join([str(item) for item in brands if str(item).strip()])
        return None

    async def _profile_api_candidates(self, page) -> List[str]:
        try:
            urls = await page.evaluate(
                """
                () => {
                    const entries = performance.getEntriesByType('resource') || [];
                    const urls = [];
                    for (const entry of entries) {
                        if (entry && entry.name && entry.name.includes('/creator/marketplace/profile')) {
                            urls.push(entry.name);
                        }
                    }
                    return Array.from(new Set(urls));
                }
                """
            )
            if isinstance(urls, list):
                return [str(url) for url in urls if str(url).strip()]
        except Exception:
            return []
        return []

    async def _fetch_creator_profile_api(self, page, creator_id: str) -> Optional[Dict[str, Any]]:
        candidates = await self._profile_api_candidates(page)
        if not candidates:
            try:
                await page.reload(wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
            except Exception:
                pass
            candidates = await self._profile_api_candidates(page)

        for url in reversed(candidates):
            try:
                response = await page.request.get(url)
                if response.status != 200:
                    continue
                data = await response.json()
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            profile = data.get("creator_profile") or {}
            oecuid = (
                profile.get("creator_oecuid", {}).get("value")
                if isinstance(profile, dict)
                else None
            )
            if creator_id and oecuid and str(oecuid) != str(creator_id):
                continue
            return data
        return None

    async def _check_connection_status(self, page) -> Tuple[bool, bool]:
        try:
            await page.wait_for_timeout(2000)
            messages = await page.evaluate(
                """
                () => {
                    const messages = [];
                    const containers = [
                        'div.messageList-k_OG24',
                        'div.chatd-scrollView',
                        'div[class*="message"]',
                        'div[class*="chat"]'
                    ];
                    let container = null;
                    for (const selector of containers) {
                        const element = document.querySelector(selector);
                        if (element && element.offsetParent !== null) {
                            container = element;
                            break;
                        }
                    }
                    if (!container) return messages;
                    const messageElements = container.querySelectorAll('div[class*="message"], div[class*="bubble"], pre[class*="content"]');
                    messageElements.forEach(el => {
                        const text = el.textContent?.trim();
                        if (!text || text.length < 2) return;
                        let isFromMerchant = false;
                        let current = el;
                        while (current && current !== container) {
                            const className = current.className || '';
                            const style = window.getComputedStyle(current);
                            if (className.includes('right') || className.includes('self') || style.marginLeft === 'auto') {
                                isFromMerchant = true;
                                break;
                            }
                            if (className.includes('left') || className.includes('other') || style.marginRight === 'auto') {
                                isFromMerchant = false;
                                break;
                            }
                            current = current.parentElement;
                        }
                        messages.push({ text, isFromMerchant });
                    });
                    return messages;
                }
                """
            )
            if not isinstance(messages, list):
                return False, False
            connect = any(m.get("isFromMerchant", False) for m in messages)
            reply = False
            seen_merchant = False
            for message in messages:
                if message.get("isFromMerchant", False):
                    seen_merchant = True
                elif seen_merchant:
                    reply = True
                    break
            return connect, reply
        except Exception:
            return False, False

    async def _publish_chatbot_task(
        self,
        *,
        creator_data: Dict[str, Any],
        options: ShopOutreachOptions,
    ) -> None:
        if not options.messages:
            self.logger.warning(
                "Skip chatbot publish: messages empty",
                creator_name=creator_data.get("creator_name"),
                creator_id=creator_data.get("creator_id"),
            )
            return
        await self._ensure_chatbot_publisher()
        if not self._chatbot_publisher:
            return
        if not creator_data.get("chat_url"):
            self.logger.warning(
                "Skip chatbot publish: chat_url missing",
                creator_name=creator_data.get("creator_name"),
                creator_id=creator_data.get("creator_id"),
            )
            return

        payload = {
            "taskId": str(uuid.uuid4()).upper(),
            "region": options.region,
            "creatorId": creator_data.get("creator_id"),
            "shopId": creator_data.get("shop_id"),
            "chatUrl": creator_data.get("chat_url"),
            "creatorName": creator_data.get("creator_name"),
            "accountName": options.account_name,
            "operatorId": options.operator_id,
            "messages": options.messages,
            "trace": {
                "source": "portal_tiktok_shop_creator_crawler",
                "run_id": options.task_id,
                "search_keywords": options.search_strategy.get("search_keywords")
                if isinstance(options.search_strategy, dict)
                else None,
            },
        }

        try:
            await self._chatbot_publisher.publish(payload)
            self.logger.info(
                "Shop chatbot task published",
                creator_name=creator_data.get("creator_name"),
                creator_id=creator_data.get("creator_id"),
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to publish shop chatbot task",
                creator_name=creator_data.get("creator_name"),
                creator_id=creator_data.get("creator_id"),
                error=str(exc),
            )

    async def process_single_creator(
        self,
        page,
        creator_name: str,
        options: ShopOutreachOptions,
    ) -> Optional[Dict[str, Any]]:
        detail_page = await self._open_creator_detail(page, creator_name)
        if not detail_page:
            return None

        result: Optional[Dict[str, Any]] = None
        try:
            await detail_page.bring_to_front()
            await detail_page.wait_for_load_state("domcontentloaded")
            await self._wait_for_detail_ready(detail_page, timeout_ms=8000)

            detail_url = detail_page.url or ""
            creator_id = self._extract_creator_id_from_url(detail_url)
            region = self._extract_region_from_url(detail_url) or options.region
            shop_id = await self._extract_shop_id(detail_page)
            chat_url = self._build_chat_url(shop_id, creator_id, region)

            try:
                await detail_page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                await detail_page.wait_for_timeout(1200)
                await detail_page.evaluate("() => window.scrollTo(0, 0)")
                await detail_page.wait_for_timeout(400)
            except Exception:
                pass

            profile_payload = await self._fetch_creator_profile_api(detail_page, creator_id)
            creator_profile = (
                profile_payload.get("creator_profile")
                if isinstance(profile_payload, dict)
                else {}
            )

            def value_of(field: Any) -> Optional[Any]:
                if isinstance(field, dict):
                    return field.get("value")
                return None

            api_creator_id = value_of(creator_profile.get("creator_oecuid"))
            handle = value_of(creator_profile.get("handle"))
            nickname = value_of(creator_profile.get("nickname"))
            bio = value_of(creator_profile.get("bio"))
            selection_region = value_of(creator_profile.get("selection_region")) or region
            currency = None
            region_key = str(selection_region or "").upper()
            if region_key in {"MX", "MEX"}:
                currency = "MXN"
            elif region_key in {"FR", "ES", "EU"}:
                currency = "EUR"
            follower_cnt = value_of(creator_profile.get("follower_cnt"))
            categories_value = value_of(creator_profile.get("category"))
            categories = None
            if isinstance(categories_value, list):
                names = [
                    item.get("name")
                    for item in categories_value
                    if isinstance(item, dict) and item.get("name")
                ]
                if names:
                    categories = ", ".join(names)

            search_keywords = None
            if isinstance(options.search_strategy, dict):
                search_keywords = options.search_strategy.get("search_keywords") or options.search_strategy.get(
                    "keyword"
                )
            brand_name = options.brand_name or "Not mentioned"

            metrics_raw = await self._collect_metric_values(detail_page)
            metrics_normalized = {
                self._normalize_label(label): value
                for label, value in metrics_raw.items()
            }

            def metric(label: str) -> Optional[str]:
                return metrics_normalized.get(self._normalize_label(label))

            legend_data = await self._extract_chart_legends(detail_page)

            def legend(title: str) -> List[Tuple[str, str]]:
                target = self._normalize_label(title)
                for name, pairs in legend_data.items():
                    normalized = self._normalize_label(name)
                    if normalized == target or target in normalized:
                        return pairs
                return []

            gmv_per_sales_channel = self._pairs_to_string(legend("GMV per sales channel"))
            gmv_by_product_category = self._pairs_to_string(legend("GMV by product category"))

            followers_male = None
            followers_female = None
            for label, value in legend("Follower gender"):
                lower = label.lower()
                if "male" in lower:
                    followers_male = self._percent_to_decimal(value)
                elif "female" in lower:
                    followers_female = self._percent_to_decimal(value)

            followers_18_24 = None
            followers_25_34 = None
            followers_35_44 = None
            followers_45_54 = None
            followers_55_more = None
            age_map = {
                "18-24": "followers_18_24",
                "25-34": "followers_25_34",
                "35-44": "followers_35_44",
                "45-54": "followers_45_54",
                "55+": "followers_55_more",
                "55plus": "followers_55_more",
            }
            for label, value in legend("Follower age"):
                normalized = label.replace(" ", "").replace("–", "-").replace("—", "-").lower()
                key = age_map.get(normalized)
                if not key and normalized.startswith("55"):
                    key = "followers_55_more"
                if not key:
                    continue
                decimal_value = self._percent_to_decimal(value)
                if key == "followers_18_24":
                    followers_18_24 = decimal_value
                elif key == "followers_25_34":
                    followers_25_34 = decimal_value
                elif key == "followers_35_44":
                    followers_35_44 = decimal_value
                elif key == "followers_45_54":
                    followers_45_54 = decimal_value
                elif key == "followers_55_more":
                    followers_55_more = decimal_value

            whatsapp, email = await self._extract_contact_info(detail_page)
            if not email and isinstance(bio, str) and "@" in bio:
                match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}", bio, re.I)
                if match:
                    email = match.group(0)

            top_brands = await self._extract_top_brands(detail_page)

            platform_creator_id = str(api_creator_id or creator_id or "").strip()
            platform_display_name = str(handle or creator_name or "").strip() or None
            platform_username = platform_display_name
            creator_display_name = str(creator_name or platform_display_name or nickname or "").strip() or None

            creator_row = {
                "platform": "tiktok_shop",
                "platform_creator_id": platform_creator_id or None,
                "platform_creator_display_name": platform_display_name,
                "platform_creator_username": platform_username,
                "creator_id": platform_creator_id or None,
                "creator_name": creator_display_name,
                "creator_username": platform_username,
                "creator_chaturl": chat_url,
                "search_keywords": str(search_keywords).strip() if search_keywords else None,
                "brand_name": brand_name,
                "region": selection_region,
                "currency": currency,
                "categories": categories,
                "followers": follower_cnt,
                "intro": str(bio).strip() if bio else None,
                "email": email,
                "whatsapp": whatsapp,
                "top_brands": top_brands,
                "sales_revenue": metric("GMV"),
                "sales_units_sold": metric("Items sold"),
                "sales_gpm": metric("GPM"),
                "sales_revenue_per_buyer": metric("GMV per customer"),
                "gmv_per_sales_channel": gmv_per_sales_channel,
                "gmv_by_product_category": gmv_by_product_category,
                "est_post_rate": self._percent_to_decimal(metric("Est. post rate")),
                "avg_commission_rate": self._percent_to_decimal(metric("Avg. commission rate")),
                "collab_products": metric("Products"),
                "partnered_brands": metric("Brand collaborations"),
                "product_price": metric("Product price"),
                "video_gpm": metric("Video GPM"),
                "videos": metric("Videos"),
                "avg_video_views": metric("Avg. video views"),
                "avg_video_engagement_rate": self._percent_to_decimal(metric("Avg. video engagement rate")),
                "avg_video_likes": metric("Avg. video likes"),
                "avg_video_comments": metric("Avg. video comments"),
                "avg_video_shares": metric("Avg. video shares"),
                "live_gpm": metric("LIVE GPM"),
                "live_streams": metric("LIVE streams"),
                "avg_live_views": metric("Avg. LIVE views"),
                "avg_live_engagement_rate": self._percent_to_decimal(metric("Avg. LIVE engagement rate")),
                "avg_live_likes": metric("Avg. LIVE likes"),
                "avg_live_comments": metric("Avg. LIVE comments"),
                "avg_live_shares": metric("Avg. LIVE shares"),
                "followers_male": followers_male,
                "followers_female": followers_female,
                "followers_18_24": followers_18_24,
                "followers_25_34": followers_25_34,
                "followers_35_44": followers_35_44,
                "followers_45_54": followers_45_54,
                "followers_55_more": followers_55_more,
                "crawl_date": datetime.now().date().isoformat(),
            }

            if not platform_creator_id:
                creator_row["skip_creator_upsert"] = True
            elif not profile_payload:
                creator_row["skip_creator_upsert"] = True

            if creator_row.get("platform_creator_id"):
                try:
                    await self._ingest_creator_data(creator_row, options)
                except Exception as exc:
                    self.logger.warning(
                        "Creator ingestion failed",
                        creator_id=creator_row.get("platform_creator_id"),
                        error=str(exc),
                    )

            result = dict(creator_row)
            result.update(
                {
                    "creator_name": creator_display_name or creator_name,
                    "creator_id": platform_creator_id or creator_id,
                    "chat_url": chat_url,
                    "detail_url": detail_url,
                    "shop_id": shop_id,
                    "region": selection_region
                    or (self.account_profile.region if self.account_profile else None),
                    "crawl_time": datetime.now().isoformat(timespec="seconds"),
                }
            )
        finally:
            if detail_page != page:
                try:
                    await detail_page.close()
                except Exception:
                    pass
            else:
                try:
                    for _ in range(2):
                        if "connection/creator" in (page.url or ""):
                            break
                        await page.go_back()
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass

        return result

    async def _resolve_creator_scroll_container(self, page) -> Optional[str]:
        selectors = [
            "#creator-list-content > div > div > div > div > div.arco-table.arco-table-size-default.arco-table-layout-fixed.m4b-table.m4b-table-vertical-center.styled__StyledTable-jbShvy.iWFqpX.creator-table__StyledTable-itEfyJ.ffekUY > div > div > div > div > div > div.arco-table-body",
            "#creator-list-content .arco-table-body",
            "div.creator-table__StyledTable-itEfyJ .arco-table-body",
            "div.arco-table-body",
        ]
        for selector in selectors:
            try:
                if await page.locator(selector).count():
                    return selector
            except Exception:
                continue
        return None

    async def _scroll_for_more_in_container(self, page, selector: Optional[str]) -> None:
        try:
            await page.evaluate(
                """
                (sel) => {
                    const el = sel ? document.querySelector(sel) : null;
                    const target = el || document.scrollingElement || document.body;
                    if (!target) return;
                    target.scrollTop = target.scrollHeight;
                }
                """,
                selector,
            )
            await page.wait_for_timeout(2000)
        except Exception:
            pass

    async def _scroll_to_top_in_container(self, page, selector: Optional[str]) -> None:
        try:
            await page.evaluate(
                """
                (sel) => {
                    const el = sel ? document.querySelector(sel) : null;
                    const target = el || document.scrollingElement || document.body;
                    if (!target) return;
                    target.scrollTop = 0;
                }
                """,
                selector,
            )
            await page.wait_for_timeout(1000)
        except Exception:
            pass

    async def _get_scroll_height(self, page, selector: Optional[str]) -> int:
        try:
            return await page.evaluate(
                """
                (sel) => {
                    const el = sel ? document.querySelector(sel) : null;
                    const target = el || document.scrollingElement || document.body;
                    return target ? (target.scrollHeight || 0) : 0;
                }
                """,
                selector,
            )
        except Exception:
            return 0

    async def _scroll_for_more(self, page) -> None:
        await self._scroll_for_more_in_container(page, self._creator_scroll_selector)

    async def _scroll_to_top(self, page) -> None:
        await self._scroll_to_top_in_container(page, self._creator_scroll_selector)

    async def _collect_creators_full(self, page) -> List[str]:
        self._creator_scroll_selector = await self._resolve_creator_scroll_container(page)
        creators: List[str] = []
        initial = await self._wait_for_creators(page, timeout_ms=30000)
        if initial:
            creators = list(dict.fromkeys(initial))
        stable_rounds = 0
        empty_rounds = 0
        last_count = len(creators)
        last_height = await self._get_scroll_height(page, self._creator_scroll_selector)
        max_rounds = 40
        rounds = 0
        while stable_rounds < 3 and rounds < max_rounds:
            rounds += 1
            current = await self.get_creators_in_current_page(page)
            if not current:
                empty_rounds += 1
                if empty_rounds >= 5:
                    break
                await self._scroll_for_more(page)
                continue
            empty_rounds = 0
            merged = list(dict.fromkeys(creators + current))
            await self._scroll_for_more(page)
            await page.wait_for_timeout(1500)
            height = await self._get_scroll_height(page, self._creator_scroll_selector)
            if len(merged) == last_count and height == last_height:
                stable_rounds += 1
            else:
                stable_rounds = 0
            creators = merged
            last_count = len(creators)
            last_height = height
        await self._scroll_to_top(page)
        return creators

    async def _go_next_creator_page(self, page) -> bool:
        next_btn = page.locator("li.arco-pagination-item-next").first
        if not await next_btn.count():
            return False
        try:
            await self._safe_click(next_btn)
            await page.wait_for_timeout(1500)
            return True
        except Exception:
            return False

    def _append_rows(self, rows: List[Dict[str, Any]], options: ShopOutreachOptions) -> Optional[str]:
        if not rows or not options.export_enabled:
            return None
        export_dir = Path(options.export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        if not self._export_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._export_path = str(export_dir / f"shop_creator_{ts}.csv")

        path = Path(self._export_path)
        file_exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as csvfile:
            fieldnames = sorted({k for row in rows for k in row.keys()})
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return str(path)

    def _queue_export_row(self, row: Dict[str, Any], options: ShopOutreachOptions) -> Optional[str]:
        if not options.export_enabled:
            return None
        return self._append_rows([row], options)

    def _flush_export_buffer(self, options: ShopOutreachOptions) -> Optional[str]:
        return None

    def _build_ingestion_options(self, options: ShopOutreachOptions) -> Dict[str, Any]:
        return {
            "task_id": options.task_id,
            "account_name": self.account_profile.name if self.account_profile else None,
            "region": options.region,
            "brand_name": options.brand_name,
            "search_strategy": options.search_strategy,
        }

    async def _ingest_creator_data(self, creator_data: Dict[str, Any], options: ShopOutreachOptions) -> None:
        if not options.task_id:
            options.task_id = str(uuid.uuid4()).upper()
        operator_id = self._resolve_operator_id(options)
        await self.ingestion_client.submit(
            source=self.source,
            operator_id=operator_id,
            options=self._build_ingestion_options(options),
            rows=[creator_data],
        )

    async def run_from_payload(self, body: Dict[str, Any]) -> Dict[str, Any]:
        options = self._parse_options(body or {})
        await self.initialize(options)
        if not self._page:
            raise PlaywrightError("Playwright page not initialized")

        await self.login(self._page, options)
        self._resolve_operator_id(options)
        if not await self.navigate_to_creator_connection(self._page, options.region):
            raise PlaywrightError("Failed to navigate to creator connection page")

        await self.apply_search_strategy(self._page, options.search_strategy)

        results: List[Dict[str, Any]] = []
        max_creators = max(0, int(options.max_creators or 0))

        while True:
            creators = await self._collect_creators_full(self._page)
            new_creators = [c for c in creators if c not in self.processed_creators]

            for creator_name in new_creators:
                if max_creators and len(results) >= max_creators:
                    break
                self.logger.info("Processing creator", creator_name=creator_name)
                data = await self.process_single_creator(self._page, creator_name, options)
                if data:
                    results.append(data)
                    self.processed_creators.add(creator_name)
                    export_path = self._queue_export_row(data, options)
                    if export_path:
                        self.logger.info(
                            "Exported creator",
                            path=export_path,
                            creator_name=creator_name,
                        )
                    await self._publish_chatbot_task(creator_data=data, options=options)
                else:
                    self.logger.warning(
                        "Creator processing skipped",
                        creator_name=creator_name,
                        reason="detail_or_chat_not_opened",
                    )
                    self.processed_creators.add(creator_name)
                await self._page.wait_for_timeout(1000)

            if max_creators and len(results) >= max_creators:
                break

            # 商家端列表当前不支持/无需翻页，处理完当前列表后结束
            break

        self.logger.info("Shop outreach crawl completed", count=len(results))
        return {"count": len(results), "rows": results}
