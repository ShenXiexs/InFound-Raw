from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Optional, Sequence, List, Dict, Any

from common.core.config import get_settings
from common.core.exceptions import MessageProcessingError, PlaywrightError
from common.core.logger import get_logger
from apps.portal_tiktok_sample_crawler.services.crawler_runner_service import (
    CrawlerRunnerService,
)


logger = get_logger().bind(component="sample_chatbot_dispatcher")


@dataclass
class ChatbotDispatchTask:
    task_id: str
    sample_id: Optional[str]
    platform_product_id: Optional[str]
    platform_product_name: Optional[str]
    platform_campaign_name: Optional[str]
    platform_creator_id: str
    platform_creator_username: Optional[str]
    creator_whatsapp: Optional[str]
    messages: Optional[List[Dict[str, Any]]]
    sender_id: str
    account_name: Optional[str]
    region: Optional[str]
    operator_id: Optional[str]

    @classmethod
    def from_payload(cls, payload: dict) -> "ChatbotDispatchTask":
        def _first(*keys, default=None):
            for key in keys:
                if key in payload and payload.get(key) is not None:
                    return payload.get(key)
            return default

        messages = cls._normalize_messages(payload.get("messages"))
        if not messages:
            raise ValueError("messages is required")

        sample_id = str(_first("sampleId", "sample_id") or "").strip() or None
        platform_product_id = str(
            _first("platformProductId", "platform_product_id", "productId", "product_id") or ""
        ).strip() or None

        platform_creator_id = str(
            _first("platformCreatorId", "platform_creator_id", "creatorId", "creator_id") or ""
        ).strip()
        if not platform_creator_id:
            raise ValueError("platformCreatorId is required")

        return cls(
            task_id=str(_first("taskId", "task_id") or "") or str(uuid.uuid4()).upper(),
            sample_id=sample_id,
            platform_product_id=platform_product_id,
            platform_product_name=str(
                _first("platformProductName", "platform_product_name", "productName", "product_name") or ""
            ).strip()
            or None,
            platform_campaign_name=str(
                _first("platformCampaignName", "platform_campaign_name", "campaignName", "campaign_name") or ""
            ).strip()
            or None,
            platform_creator_id=platform_creator_id,
            platform_creator_username=str(
                _first(
                    "platformCreatorUsername",
                    "platform_creator_username",
                    "creatorUsername",
                    "creator_username",
                )
                or ""
            ).strip()
            or None,
            creator_whatsapp=str(
                _first("creatorWhatsapp", "creator_whatsapp", "whatsapp") or ""
            ).strip()
            or None,
            messages=messages,
            sender_id=str(payload.get("from") or ""),
            account_name=_first("accountName", "account_name"),
            region=str(payload.get("region") or "").upper(),
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


class ChatbotDispatcherService:
    """Consume queued chat tasks and send messages via Playwright.

    Important: this consumer must be "sender-only" and does NOT query MySQL.
    All business fields (including messages) should be provided in MQ payload.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = logger
        self.default_region = str(
            getattr(
                self.settings,
                "CHATBOT_DEFAULT_REGION",
                getattr(self.settings, "SAMPLE_DEFAULT_REGION", "MX"),
            )
            or "MX"
        ).upper()
        self.account_name = getattr(self.settings, "CHATBOT_ACCOUNT_NAME", None)
        self.home_path = str(getattr(self.settings, "CHATBOT_HOME_PATH", "/home") or "/home")
        self.min_prefix_len = int(
            getattr(self.settings, "CHATBOT_MIN_PREFIX_LENGTH", 3) or 3
        )
        self.input_wait_timeout_seconds = int(
            getattr(self.settings, "CHATBOT_INPUT_WAIT_TIMEOUT_SECONDS", 150) or 150
        )
        self._runner = CrawlerRunnerService()
        self._browser_ready = False
        self._playwright_lock = asyncio.Lock()
        self._dispatch_lock = asyncio.Lock()

    async def prewarm(self) -> None:
        # Prewarming navigates the shared main page; serialize it with dispatch()
        # to avoid racing a real task (which can cause navigation/DOM instability).
        async with self._dispatch_lock:
            region = self.default_region
            try:
                await self._ensure_browser(region, self.account_name)
                page = await self._runner.ensure_main_page()
                await self._return_to_home(page, region)
                self.logger.info(
                    "Chatbot browser prewarmed", region=region, home_path=self.home_path
                )
            except Exception:
                self.logger.warning("Chatbot browser prewarm failed", exc_info=True)

    async def dispatch(self, task: ChatbotDispatchTask) -> None:
        async with self._dispatch_lock:
            region = task.region or self.default_region
            message_texts = self._render_messages(task.messages or [])
            if not message_texts:
                raise MessageProcessingError("No messages to send")

            await self._ensure_browser(region, task.account_name)
            partner_id = str(getattr(getattr(self._runner, "account_profile", None), "creator_id", "") or "")
            success = await self._send_chat_messages(
                partner_id=partner_id,
                creator_id=task.platform_creator_id,
                region=region,
                messages=message_texts,
            )
            if not success:
                if not self._runner.has_live_session():
                    await self._runner.close()
                    self._browser_ready = False
                raise MessageProcessingError("Failed to send chat message")

    async def close(self) -> None:
        async with self._playwright_lock:
            await self._runner.close()
            self._browser_ready = False

    def _render_messages(self, messages: Sequence[Dict[str, Any]]) -> List[str]:
        rendered: List[str] = []
        for msg in messages:
            if isinstance(msg, str):
                content = msg.strip()
                if content:
                    rendered.append(content)
                continue
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                rendered.append(content.strip())
                continue
            meta = msg.get("meta") if isinstance(msg.get("meta"), dict) else {}
            fallback = meta.get("fallbackText") or meta.get("fallback_text")
            if isinstance(fallback, str) and fallback.strip():
                rendered.append(fallback.strip())
            else:
                self.logger.warning(
                    "Skipped message with empty content",
                    message_type=str(msg.get("type") or "text"),
                )
        return rendered

    async def _ensure_browser(self, region: str, account_name: Optional[str]) -> None:
        desired_account = account_name or self.account_name
        async with self._playwright_lock:
            if self._browser_ready and not self._runner.has_live_session():
                await self._runner.close()
                self._browser_ready = False

            if not self._browser_ready:
                profile = self._runner.resolve_profile(region, desired_account)
                await self._runner.initialize(profile)
                self._browser_ready = True
            elif not self._runner.matches_profile(region, desired_account):
                await self._runner.close()
                self._browser_ready = False
                profile = self._runner.resolve_profile(region, desired_account)
                await self._runner.initialize(profile)
                self._browser_ready = True
            try:
                await self._runner.ensure_account_session(region, desired_account)
            except PlaywrightError as exc:
                self.logger.warning(
                    "Chatbot browser session invalid; resetting",
                    region=region,
                    account_name=desired_account,
                    exc_info=True,
                )
                await self._runner.close()
                self._browser_ready = False
                raise PlaywrightError("Browser session reset; drop current task") from exc

    async def _send_chat_messages(
        self, *, partner_id: str, creator_id: str, region: str, messages: Sequence[str]
    ) -> bool:
        page = await self._runner.ensure_main_page()
        try:
            page = await self._navigate_to_chat_page(
                page,
                partner_id=partner_id,
                creator_id=creator_id,
                region=region,
            )
            if not page:
                return False
            input_waited = False
            for idx, message in enumerate(messages, start=1):
                sent = False
                for attempt in range(1, 4):
                    # Browser/page can be closed by crashes or manual intervention; try to recover.
                    if not page or page.is_closed():
                        page = await self._runner.ensure_main_page()
                        page = await self._navigate_to_chat_page(
                            page,
                            partner_id=partner_id,
                            creator_id=creator_id,
                            region=region,
                        )
                        if not page:
                            return False
                    baseline = await self._count_merchant_messages(page)
                    typed = await self._fill_chat_input(page, message)
                    if not typed:
                        self.logger.warning(
                            "Chat input not ready",
                            attempt=attempt,
                            creator_id=creator_id,
                        )
                        if not input_waited:
                            input_waited = True
                            ready = await self._wait_for_chat_input(
                                page, timeout_seconds=self.input_wait_timeout_seconds
                            )
                            if ready:
                                continue
                            self.logger.warning(
                                "Chat input unavailable; skipping remaining messages",
                                creator_id=creator_id,
                                waited_seconds=self.input_wait_timeout_seconds,
                            )
                            return True
                        return True
                    # Some variants require clicking a send button instead of pressing Enter.
                    await self._click_send_button_if_present(page)
                    sent = await self._verify_message_sent(page, baseline)
                    if sent:
                        self.logger.info(
                            "Chat message sent",
                            region=region,
                            creator_id=creator_id,
                            order=idx,
                        )
                        break
                    self.logger.warning(
                        "Message verification failed, retrying",
                        attempt=attempt,
                        order=idx,
                        creator_id=creator_id,
                    )
                    await page.wait_for_timeout(1500)
                if not sent:
                    return False
            return True
        except Exception:
            self.logger.error("Sending chat message failed", exc_info=True)
            return False
        finally:
            await self._return_to_home(page, region)

    def _base_domain_for_region(self, region: str) -> str:
        region_upper = str(region or "").upper()
        if region_upper in {"FR"}:
            return "partner.eu.tiktokshop.com"
        return "partner.tiktokshop.com"

    def _home_url(self, region: str) -> str:
        base_domain = self._base_domain_for_region(region)
        path = self.home_path if self.home_path.startswith("/") else f"/{self.home_path}"
        return f"https://{base_domain}{path}"

    async def _return_to_home(self, page, region: str) -> None:
        """Keep a resident page open by returning it to home after each task."""
        try:
            if not page or page.is_closed():
                return
            home_url = self._home_url(region)
            await page.goto(home_url, wait_until="load", timeout=60_000)
            await page.wait_for_timeout(800)
        except Exception:
            self.logger.warning("Failed to return to home (ignored)", region=region, exc_info=True)

    async def _navigate_to_chat_page(self, page, *, partner_id: str, creator_id: str, region: str):
        if not creator_id:
            self.logger.error("Missing creator_id; cannot navigate to chat page")
            return None

        region_upper = str(region or "").upper()
        market_mapping = {
            "MX": "19",
            "FR": "17",
        }
        market_id = market_mapping.get(region_upper, "19")

        base_domain = self._base_domain_for_region(region_upper)

        chat_url = (
            f"https://{base_domain}/partner/im?"
            f"creator_id={creator_id}&market={market_id}&enter_from=find_creator_detail"
        )

        self.logger.info(
            "Navigate to chat page",
            partner_id=partner_id,
            creator_id=creator_id,
            region=region_upper,
            chat_url=chat_url,
        )

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    try:
                        context = page.context
                        new_page = await context.new_page()
                        try:
                            await page.close()
                        except Exception:
                            pass
                        page = new_page
                        # keep runner main page pointer in sync to avoid leaving orphan tabs
                        try:
                            setattr(self._runner, "_main_page", page)
                        except Exception:
                            pass
                        await page.wait_for_timeout(1000)
                    except Exception:
                        pass

                await page.goto(chat_url, wait_until="networkidle", timeout=90_000)
                await page.wait_for_timeout(2000)
                try:
                    setattr(self._runner, "_main_page", page)
                except Exception:
                    pass
                return page
            except Exception as exc:
                self.logger.warning(
                    "Chat page navigation failed",
                    attempt=attempt,
                    error=str(exc),
                    creator_id=creator_id,
                    region=region_upper,
                )
                if attempt < max_attempts:
                    await page.wait_for_timeout(3000)
        return None

    @staticmethod
    def _chat_input_selectors() -> List[str]:
        return [
            'textarea[placeholder="Send a message"]',
            'textarea[placeholder*="Send a message"]',
            '#im_sdk_chat_input textarea',
            'textarea[placeholder*="message" i]',
            'div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"]',
        ]

    async def _wait_for_chat_input(self, page, *, timeout_seconds: int) -> bool:
        if not page or page.is_closed():
            return False
        deadline = asyncio.get_running_loop().time() + max(int(timeout_seconds), 0)
        selectors = self._chat_input_selectors()
        while asyncio.get_running_loop().time() < deadline:
            for selector in selectors:
                try:
                    locator = page.locator(selector).first
                    if await page.locator(selector).count() == 0:
                        continue
                    if await locator.is_visible():
                        return True
                except Exception:
                    continue
            try:
                if page.is_closed():
                    return False
                await page.wait_for_timeout(2000)
            except Exception:
                return False
        return False

    async def _fill_chat_input(self, page, text: str) -> bool:
        if not text:
            return False
        selectors = self._chat_input_selectors()
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await page.locator(selector).count() == 0:
                    continue
                await locator.wait_for(state="visible", timeout=4_000)
                await locator.click()
                # textarea supports fill(); contenteditable prefers type()
                if "contenteditable" in selector:
                    await locator.fill("")  # best-effort clear
                    await locator.type(text, delay=5)
                else:
                    await locator.fill(text)
                await page.wait_for_timeout(200)
                await locator.press("Enter")
                return True
            except Exception:
                continue
        try:
            await page.evaluate(
                """(value) => {
                    const ta = document.querySelector(
                        '#im_sdk_chat_input textarea, textarea#imTextarea, textarea[placeholder*="message" i], textarea'
                    );
                    if (ta) {
                        ta.focus();
                        ta.value = value;
                        ta.dispatchEvent(new Event('input', { bubbles: true }));
                        return true;
                    }
                    return false;
                }""",
                text,
            )
            await page.keyboard.press("Enter")
            return True
        except Exception:
            return False

    async def _click_send_button_if_present(self, page) -> None:
        selectors = [
            'button:has-text("Send")',
            'button[aria-label*="Send" i]',
            'button[data-e2e*="send" i]',
            'button[type="submit"]',
        ]
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if await page.locator(selector).count() == 0:
                    continue
                if not await button.is_visible():
                    continue
                await button.click(timeout=800)
                await page.wait_for_timeout(200)
                return
            except Exception:
                continue

    async def _verify_message_sent(self, page, baseline: int) -> bool:
        for _ in range(8):
            try:
                has_message = await page.evaluate(
                    """(threshold) => {
                        const selectors = [
                            'div.index-module__messageList--GBz6X',
                            'div.messageList-k_OG24',
                            'div.chatd-scrollView',
                            'div[class*="messageList" i]',
                            'div[class*="message-list" i]',
                        ];
                        for (const selector of selectors) {
                            const container = document.querySelector(selector);
                            if (!container) continue;
                            const messages = container.querySelectorAll(
                              'div.chatd-message--right, div[class*="message" i][class*="right" i], div[class*="right" i][class*="chat" i]'
                            );
                            if (messages && messages.length > threshold) {
                                return true;
                            }
                        }
                        return false;
                    }""",
                    baseline,
                )
                if has_message:
                    return True
            except Exception as exc:
                # When the page/context/browser is closed, playwright raises TargetClosedError.
                # Treat it as a send failure so caller may reopen and retry.
                if "TargetClosedError" in str(exc) or "Target page" in str(exc):
                    return False
            try:
                if page.is_closed():
                    return False
                await page.wait_for_timeout(1_000)
            except Exception:
                return False
        return False

    async def _count_merchant_messages(self, page) -> int:
        try:
            return await page.evaluate(
                """() => {
                    const selectors = [
                        'div.index-module__messageList--GBz6X',
                        'div.messageList-k_OG24',
                        'div.chatd-scrollView',
                        'div[class*="messageList" i]',
                        'div[class*="message-list" i]',
                    ];
                    for (const selector of selectors) {
                        const container = document.querySelector(selector);
                        if (!container) continue;
                        const messages = container.querySelectorAll(
                          'div.chatd-message--right, div[class*="message" i][class*="right" i], div[class*="right" i][class*="chat" i]'
                        );
                        return (messages && messages.length) ? messages.length : 0;
                    }
                    return 0;
                }"""
            )
        except Exception:
            return 0
