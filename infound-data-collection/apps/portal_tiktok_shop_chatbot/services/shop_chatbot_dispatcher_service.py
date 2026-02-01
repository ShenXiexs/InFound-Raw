from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from playwright.async_api import async_playwright

from common.core.config import get_settings
from common.core.exceptions import MessageProcessingError, PlaywrightError
from common.core.logger import get_logger
from common.playwright.shop_login_manager import ShopLoginManager
from apps.portal_tiktok_sample_crawler.services.email_verifier import GmailVerificationCode

logger = get_logger().bind(component="shop_chatbot_dispatcher")


@dataclass
class ShopChatbotDispatchTask:
    task_id: str
    region: Optional[str]
    creator_id: Optional[str]
    shop_id: Optional[str]
    chat_url: Optional[str]
    creator_name: Optional[str]
    messages: List[Dict[str, Any]]
    account_name: Optional[str]
    operator_id: Optional[str]

    @classmethod
    def from_payload(cls, payload: dict) -> "ShopChatbotDispatchTask":
        def _first(*keys, default=None):
            for key in keys:
                if key in payload and payload.get(key) is not None:
                    return payload.get(key)
            return default

        messages = cls._normalize_messages(payload.get("messages"))
        if not messages:
            raise ValueError("messages is required")

        creator_id = str(_first("creatorId", "creator_id", "platformCreatorId", "platform_creator_id") or "").strip()
        shop_id = str(_first("shopId", "shop_id") or "").strip() or None
        chat_url = str(_first("chatUrl", "chat_url") or "").strip() or None
        if not chat_url and not creator_id:
            raise ValueError("creatorId or chatUrl is required")

        return cls(
            task_id=str(_first("taskId", "task_id") or "") or str(uuid.uuid4()).upper(),
            region=str(_first("region") or "").strip().upper() or None,
            creator_id=creator_id or None,
            shop_id=shop_id,
            chat_url=chat_url,
            creator_name=str(_first("creatorName", "creator_name") or "").strip() or None,
            messages=messages,
            account_name=_first("accountName", "account_name"),
            operator_id=_first("operatorId", "operator_id"),
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


class ShopChatbotDispatcherService:
    """Consume queued shop chat tasks and send messages via Playwright."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = logger
        self.default_region = str(
            getattr(self.settings, "SHOP_CHATBOT_DEFAULT_REGION", "MX") or "MX"
        ).upper()
        self.account_name = getattr(self.settings, "SHOP_CHATBOT_ACCOUNT_NAME", None)
        self.account_config_path = Path(
            getattr(self.settings, "SHOP_CHATBOT_ACCOUNT_CONFIG_PATH", "configs/accounts.json")
        )
        self.accounts_data = self._load_accounts_config()

        self.login_manager = ShopLoginManager(
            login_url=str(getattr(self.settings, "SHOP_CHATBOT_LOGIN_URL", "") or "https://seller-mx.tiktok.com/account/login"),
            manual_login_default=bool(getattr(self.settings, "SHOP_CHATBOT_MANUAL_LOGIN", False)),
            manual_login_timeout_ms=int(
                getattr(self.settings, "SHOP_CHATBOT_MANUAL_LOGIN_TIMEOUT_SECONDS", 300) or 300
            )
            * 1000,
            manual_email_code_input=bool(
                getattr(self.settings, "SHOP_CHATBOT_MANUAL_EMAIL_CODE_INPUT", True)
            ),
            manual_email_code_input_timeout_seconds=int(
                getattr(self.settings, "SHOP_CHATBOT_MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS", 180)
            ),
            manual_email_code_only=bool(
                getattr(self.settings, "SHOP_CHATBOT_MANUAL_EMAIL_CODE_INPUT", True)
            ),
        )

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False
        self.account_profile = None
        self.gmail_verifier: Optional[GmailVerificationCode] = None

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

    def _select_account(self, region: Optional[str], account_name: Optional[str]):
        desired_region = (region or self.default_region or "MX").upper()
        if account_name:
            for account in self.accounts_data:
                if account_name.lower() == str(account.get("name", "")).lower():
                    enabled = account.get("enabled", True)
                    if not enabled:
                        raise PlaywrightError(f"Account {account_name} is disabled")
                    return {
                        "name": account.get("name", ""),
                        "login_email": account.get("login_email", ""),
                        "login_password": account.get("login_password"),
                        "gmail_username": account.get("gmail_username", ""),
                        "gmail_app_password": account.get("gmail_app_password", ""),
                        "region": str(account.get("region", desired_region)).upper(),
                        "enabled": enabled,
                    }
            raise PlaywrightError(f"Account {account_name} not found in config")

        default_email = str(getattr(self.settings, "SHOP_CHATBOT_LOGIN_EMAIL", "") or "").strip()
        if default_email:
            return {
                "name": "DEFAULT",
                "login_email": default_email,
                "login_password": getattr(self.settings, "SHOP_CHATBOT_LOGIN_PASSWORD", None),
                "gmail_username": str(getattr(self.settings, "SHOP_CHATBOT_GMAIL_USERNAME", "") or ""),
                "gmail_app_password": str(getattr(self.settings, "SHOP_CHATBOT_GMAIL_APP_PASSWORD", "") or ""),
                "region": desired_region,
                "enabled": True,
            }

        for account in self.accounts_data:
            account_region = str(account.get("region", "")).upper()
            enabled = account.get("enabled", True)
            if enabled and account_region == desired_region:
                return {
                    "name": account.get("name", ""),
                    "login_email": account.get("login_email", ""),
                    "login_password": account.get("login_password"),
                    "gmail_username": account.get("gmail_username", ""),
                    "gmail_app_password": account.get("gmail_app_password", ""),
                    "region": account_region,
                    "enabled": enabled,
                }

        return {
            "name": "DEFAULT",
            "login_email": str(getattr(self.settings, "SHOP_CHATBOT_LOGIN_EMAIL", "") or ""),
            "login_password": getattr(self.settings, "SHOP_CHATBOT_LOGIN_PASSWORD", None),
            "gmail_username": str(getattr(self.settings, "SHOP_CHATBOT_GMAIL_USERNAME", "") or ""),
            "gmail_app_password": str(getattr(self.settings, "SHOP_CHATBOT_GMAIL_APP_PASSWORD", "") or ""),
            "region": desired_region,
            "enabled": True,
        }

    async def prewarm(self) -> None:
        await self._ensure_browser()

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
        self._logged_in = False

    async def dispatch(self, task: ShopChatbotDispatchTask) -> None:
        region = task.region or self.default_region
        await self._ensure_browser()
        await self._ensure_logged_in(region=region, account_name=task.account_name)
        page = await self._ensure_main_page()

        chat_url = self._build_chat_url(task, region=region)
        if not chat_url:
            raise MessageProcessingError("chat_url is required")

        self.logger.info(
            "Navigate to shop chat",
            task_id=task.task_id,
            creator_id=task.creator_id,
            chat_url=chat_url,
        )
        await page.goto(chat_url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(1500)

        message_texts = self._render_messages(task.messages)
        if not message_texts:
            raise MessageProcessingError("No messages to send")

        sent = await self._send_chat_messages(page, message_texts)
        if not sent:
            raise MessageProcessingError("Failed to send chat messages")

    async def _ensure_browser(self) -> None:
        if self._playwright:
            return
        headless = bool(getattr(self.settings, "PLAYWRIGHT_HEADLESS", False))
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(45_000)

    async def _ensure_main_page(self):
        if not self._page or self._page.is_closed():
            self._page = await self._context.new_page()
            self._page.set_default_timeout(45_000)
        return self._page

    async def _ensure_logged_in(self, *, region: str, account_name: Optional[str]) -> None:
        if self._page and self._logged_in:
            try:
                if await self.login_manager.is_logged_in(self._page):
                    return
            except Exception:
                pass

        self.account_profile = self._select_account(region, account_name)
        if self.account_profile.get("gmail_username") and self.account_profile.get("gmail_app_password"):
            self.gmail_verifier = GmailVerificationCode(
                username=self.account_profile.get("gmail_username"),
                app_password=self.account_profile.get("gmail_app_password"),
            )
        else:
            self.gmail_verifier = None

        await self.login_manager.perform_login(
            self._page,
            self.account_profile,
            self.gmail_verifier,
        )
        self._logged_in = True

    def _build_chat_url(self, task: ShopChatbotDispatchTask, *, region: str) -> Optional[str]:
        if task.chat_url:
            return task.chat_url
        if not task.shop_id or not task.creator_id:
            return None
        region_key = (region or self.default_region or "MX").upper()
        return (
            "https://affiliate.tiktok.com/seller/im"
            f"?shop_id={task.shop_id}&creator_id={task.creator_id}"
            f"&enter_from=affiliate_creator_details&shop_region={region_key}"
        )

    def _render_messages(self, messages: Sequence[Dict[str, Any]]) -> List[str]:
        rendered: List[str] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            rendered.append(content)
        return rendered

    async def _send_chat_messages(self, page, messages: Sequence[str]) -> bool:
        if not messages:
            return False
        for idx, message in enumerate(messages, start=1):
            ok = await self._fill_chat_input(page, message)
            if not ok:
                self.logger.warning("Chat input unavailable", message_index=idx)
                return False
            try:
                await page.keyboard.press("Enter")
            except Exception:
                try:
                    await page.locator("button:has-text(\"Send\")").first.click()
                except Exception:
                    pass
            await page.wait_for_timeout(800)
        return True

    async def _fill_chat_input(self, page, message: str) -> bool:
        selectors = [
            'textarea[placeholder="Send a message"]',
            'textarea[placeholder*="Send a message"]',
            'textarea[placeholder*="message" i]',
            '#im_sdk_chat_input textarea',
            'textarea#imTextarea',
            'textarea',
        ]
        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            for selector in selectors:
                locator = page.locator(selector).first
                try:
                    if await locator.count():
                        await locator.fill(message)
                        return True
                except Exception:
                    continue
            await asyncio.sleep(0.5)
        return False
