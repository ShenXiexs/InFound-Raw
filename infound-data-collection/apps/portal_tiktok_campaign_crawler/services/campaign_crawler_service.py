from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from common.core.config import get_settings
from common.core.exceptions import PlaywrightError
from common.core.logger import get_logger
from apps.portal_tiktok_sample_crawler.services.email_verifier import GmailVerificationCode

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


class CampaignCrawlerService:
    """Campaign crawler that validates TikTok Shop Partner Center login."""

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
        self.login_url_override = str(
            getattr(self.settings, "CAMPAIGN_LOGIN_URL", "") or ""
        ).strip()

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

        self.gmail_verifier: Optional[GmailVerificationCode] = None
        if self.gmail_username and self.gmail_app_password:
            self.gmail_verifier = GmailVerificationCode(
                self.gmail_username, self.gmail_app_password
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
        if not self.login_email:
            raise PlaywrightError("CAMPAIGN_LOGIN_EMAIL is required")
        if not self.gmail_verifier and not self.manual_email_code_input:
            raise PlaywrightError("Gmail verifier or manual code input is required")

        max_retries = 5
        for attempt in range(max_retries):
            self.logger.info("Login attempt", attempt=attempt + 1, max_retries=max_retries)
            try:
                await page.goto(self._login_url(), wait_until="networkidle")
                if await self._is_logged_in(page):
                    self.logger.info("Already logged in")
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

                verification_code = await self._prompt_verification_code()
                if not verification_code and self.gmail_verifier:
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

    async def run(self) -> Dict[str, Any]:
        await self.initialize()
        if not self._page:
            raise PlaywrightError("Playwright page not initialized")
        if not await self.login(self._page):
            raise PlaywrightError("Login failed")
        return {"login": "ok"}

    async def run_from_payload(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self.run()

    async def close(self) -> None:
        await _close_with_timeout(self._page, "page")
        await _close_with_timeout(self._context, "context")
        await _close_with_timeout(self._browser, "browser")
        await _close_with_timeout(self._playwright, "playwright")
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
