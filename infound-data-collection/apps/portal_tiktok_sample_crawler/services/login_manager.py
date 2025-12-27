from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse

from common.core.exceptions import PlaywrightError
from common.core.logger import get_logger

logger = get_logger()


DumpDebugCallback = Callable[[Any, str], Awaitable[None]]


class LoginManager:
    """Encapsulated Playwright login flow so it can be reused/overridden by other apps."""

    def __init__(
            self,
            login_url: str,
            search_input_selector: str,
            manual_login_default: bool = False,
            manual_email_code_input: bool = False,
            manual_email_code_input_timeout_seconds: int = 180,
    ) -> None:
        self.login_url = login_url
        self.search_input_selector = search_input_selector
        # Force automated login unless manual mode is explicitly enabled.
        self.manual_login_default = bool(manual_login_default)
        self.manual_email_code_input = bool(manual_email_code_input)
        self.manual_email_code_input_timeout_seconds = int(manual_email_code_input_timeout_seconds or 180)

    async def _prompt_verification_code(self) -> Optional[str]:
        """Prompt user to enter the email verification code (fallback when IMAP is unavailable)."""
        if not self.manual_email_code_input:
            return None
        prompt = "Enter the TikTok email code (6 letters/digits). Press Enter to skip: "
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(input, prompt),
                timeout=float(self.manual_email_code_input_timeout_seconds),
            )
        except asyncio.TimeoutError:
            logger.warning("Manual code entry timed out; skipping this login attempt")
            return None
        except EOFError:
            logger.warning("Manual input unavailable (non-interactive); skipping this login attempt")
            return None
        except Exception as exc:
            logger.warning("Manual code entry failed: %s", exc)
            return None

        code = str(raw or "").strip().upper()
        if not code:
            return None
        if not re.fullmatch(r"[A-Z0-9]{6}", code):
            logger.warning("Invalid code format (expect 6 letters/digits); retrying automatically")
            return None
        return code

    async def is_logged_in(self, page) -> bool:
        """Basic login detection: domain + more stable dashboard markers."""
        host = (urlparse(page.url or "").hostname or "").lower()
        if not (
                host.endswith("partner.tiktokshop.com")
                or host.endswith("partner.eu.tiktokshop.com")
                or "partner" in host
        ):
            return False

        markers = [
            self.search_input_selector,
            'input[placeholder="Search campaign ID"]',
            'input[placeholder*="Search"]',
            'text="Sample requests"',
            'text="Samples"',
            'a[href*="affiliate-campaign"]',
            'text="Find creators"',
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
        # Fallback: if already on partner domain and not on login path, treat as logged in.
        path = (urlparse(page.url or "").path or "").lower()
        if "login" not in path:
            return True
        return False

    async def wait_for_manual_login(self, page, timeout: int = 300_000) -> None:
        """Manual login wait loop."""
        logger.info("Manual login mode enabled, please complete login in the opened browser...")
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) * 1000 < timeout:
            try:
                if await self.is_logged_in(page):
                    logger.info("Manual login detected, continuing.")
                    return
            except Exception:
                pass
            await asyncio.sleep(2)
        raise PlaywrightError("Manual login timeout")

    async def perform_login(
            self,
            page,
            account_profile: Any,
            gmail_verifier: Any,
            dump_debug_cb: Optional[DumpDebugCallback] = None,
    ) -> None:
        """Perform login using email code flow."""
        await page.goto(self.login_url, wait_until="load")
        if await self.is_logged_in(page):
            logger.info("Login check passed: already logged in (dashboard marker detected)")
            return

        if self.manual_login_default:
            await self.wait_for_manual_login(page)
            return

        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                logger.info("Login attempt %s/%s", attempt, max_retries)
                selectors_login_with_code = [
                    'text="Log in with code"',
                    'text="通过验证码登录"',
                ]
                for sel in selectors_login_with_code:
                    try:
                        await page.wait_for_selector(sel, timeout=10_000)
                        await page.get_by_text(sel.replace('text="', '').replace('"', "")).click()
                        break
                    except Exception:
                        continue
                else:
                    raise PlaywrightError("Login-with-code button not found")

                email_input_selectors = ["#email input", 'input[name="email"]', 'input[type="email"]']
                for selector in email_input_selectors:
                    try:
                        await page.fill(selector, account_profile.login_email)
                        break
                    except Exception:
                        continue

                send_btn_selectors = [
                    'div[starling-key="profile_edit_userinfo_send_code"]',
                    'button:has-text("Send code")',
                    'button:has-text("发送验证码")',
                ]
                send_btn = None
                for sel in send_btn_selectors:
                    candidate = page.locator(sel).first
                    if await candidate.count():
                        send_btn = candidate
                        break
                if not send_btn:
                    raise PlaywrightError("Send code button not found")
                await send_btn.wait_for(state="visible", timeout=10_000)
                await send_btn.click()
                await page.wait_for_timeout(1000)

                # IMAP fetch can be blocked; allow manual input for local debugging.
                if self.manual_email_code_input:
                    verification_code = await self._prompt_verification_code()
                    if not verification_code:
                        verification_code = await asyncio.to_thread(
                            gmail_verifier.get_verification_code,
                            max_attempts=1,
                            check_interval=1,
                        )
                else:
                    verification_code = await asyncio.to_thread(gmail_verifier.get_verification_code)

                if not verification_code:
                    raise PlaywrightError("Failed to fetch verification code")

                await page.fill("#emailCode_input", verification_code)
                await page.locator('button[starling-key="account_login_btn_loginform_login_text"]').click()
                # Wait after submit to allow SSO redirect to settle.
                await page.wait_for_timeout(8000)
                # If redirected to partner domain and not on login path, treat as success.
                host = (urlparse(page.url or "").hostname or "").lower()
                path = (urlparse(page.url or "").path or "").lower()
                if (
                        ("partner.tiktokshop.com" in host or "partner.eu.tiktokshop.com" in host or "partner" in host)
                        and "login" not in path
                ):
                    logger.info("Login succeeded; redirected to partner domain")
                    return

                for _ in range(20):  # up to ~40s
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5_000)
                    except Exception:
                        pass
                    if await self.is_logged_in(page):
                        logger.info("Login succeeded; login markers detected")
                        return
                    await asyncio.sleep(2)
                raise PlaywrightError("Login submitted but no logged-in markers detected")
            except Exception as exc:
                logger.warning("Login attempt %s failed: %s", attempt, exc)
                if dump_debug_cb:
                    try:
                        await dump_debug_cb(page, f"login_attempt_{attempt}")
                    except Exception:
                        pass
                await asyncio.sleep(3)
                await page.goto(self.login_url, wait_until="load")
        raise PlaywrightError("Login failed")
