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
        # 强制自动登录路径；若确需手动模式应显式传 True
        self.manual_login_default = bool(manual_login_default)
        self.manual_email_code_input = bool(manual_email_code_input)
        self.manual_email_code_input_timeout_seconds = int(manual_email_code_input_timeout_seconds or 180)

    async def _prompt_verification_code(self) -> Optional[str]:
        """Prompt user to enter the email verification code (fallback when IMAP is unavailable)."""
        if not self.manual_email_code_input:
            return None
        prompt = "请输入 TikTok 邮箱验证码（6位字母/数字），直接回车表示放弃本次： "
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(input, prompt),
                timeout=float(self.manual_email_code_input_timeout_seconds),
            )
        except asyncio.TimeoutError:
            logger.warning("手动输入验证码超时，放弃本次登录尝试")
            return None
        except EOFError:
            logger.warning("无法读取手动输入（非交互环境），放弃本次登录尝试")
            return None
        except Exception as exc:
            logger.warning("手动输入验证码失败: %s", exc)
            return None

        code = str(raw or "").strip().upper()
        if not code:
            return None
        if not re.fullmatch(r"[A-Z0-9]{6}", code):
            logger.warning("验证码格式不正确（期望 6 位字母/数字），将继续自动重试")
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
        # 兜底：域名已是 partner 且 URL 不包含 login 时，也视为登录成功
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
            logger.info("登录检测通过：已在登录状态（重定向后直接命中 dashboard 标识）")
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
                    raise PlaywrightError("找不到“通过验证码登录”按钮")

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
                    raise PlaywrightError("找不到发送验证码按钮")
                await send_btn.wait_for(state="visible", timeout=10_000)
                await send_btn.click()
                await page.wait_for_timeout(1000)

                # IMAP 拉取验证码可能受网络限制影响；开启手动输入时优先提示用户（本地调试更快）。
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
                # 登录提交后留足 8s，让 SSO 重定向稳定再检查标识
                await page.wait_for_timeout(8000)
                # 如果已经跳到 partner 域且非 login 路径，直接视为成功
                host = (urlparse(page.url or "").hostname or "").lower()
                path = (urlparse(page.url or "").path or "").lower()
                if (
                        ("partner.tiktokshop.com" in host or "partner.eu.tiktokshop.com" in host or "partner" in host)
                        and "login" not in path
                ):
                    logger.info("登录成功，已重定向到 partner 域")
                    return

                for _ in range(20):  # 最长 ~40s
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5_000)
                    except Exception:
                        pass
                    if await self.is_logged_in(page):
                        logger.info("登录成功，检测到登录标识")
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
        raise PlaywrightError("登录失败")
