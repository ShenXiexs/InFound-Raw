from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from common.core.config import get_settings
from common.core.exceptions import MessageProcessingError, PlaywrightError
from common.core.logger import get_logger
from apps.sample_chatbot.services.chatbot_dispatcher_service import (
    ChatbotDispatcherService,
)
from apps.portal_tiktok_creator_crawler.services.creator_ingestion_client import (
    CreatorIngestionClient,
)
from apps.portal_tiktok_creator_crawler.services.outreach_task_client import (
    OutreachTaskClient,
)

from .creator_history_client import CreatorHistoryClient

logger = get_logger().bind(component="outreach_chatbot_dispatcher")


@dataclass
class OutreachChatbotTask:
    task_id: str
    outreach_task_id: Optional[str]
    platform_creator_id: str
    platform_creator_username: Optional[str]
    platform_creator_display_name: Optional[str]
    creator_name: Optional[str]
    creator_username: Optional[str]
    region: Optional[str]
    account_name: Optional[str]
    operator_id: Optional[str]
    brand_name: Optional[str]
    only_first: Optional[Any]
    task_metadata: Dict[str, Any]

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "OutreachChatbotTask":
        def _first(*keys, default=None):
            for key in keys:
                if key in payload and payload.get(key) is not None:
                    return payload.get(key)
            return default

        creator_id = str(
            _first("platformCreatorId", "platform_creator_id", "creatorId", "creator_id") or ""
        ).strip()
        if not creator_id:
            raise ValueError("platformCreatorId is required")

        metadata = _first("taskMetadata", "task_metadata", "metadata", default={})
        if not isinstance(metadata, dict):
            metadata = {}

        return cls(
            task_id=str(_first("taskId", "task_id") or "") or str(uuid.uuid4()).upper(),
            outreach_task_id=_first("outreachTaskId", "outreach_task_id"),
            platform_creator_id=creator_id,
            platform_creator_username=str(
                _first("platformCreatorUsername", "platform_creator_username", "creatorUsername", "creator_username")
                or ""
            ).strip()
            or None,
            platform_creator_display_name=str(
                _first(
                    "platformCreatorDisplayName",
                    "platform_creator_display_name",
                    "creatorName",
                    "creator_name",
                )
                or ""
            ).strip()
            or None,
            creator_name=str(_first("creatorName", "creator_name") or "").strip() or None,
            creator_username=str(_first("creatorUsername", "creator_username") or "").strip() or None,
            region=str(_first("region") or "").strip().upper() or None,
            account_name=_first("accountName", "account_name"),
            operator_id=_first("operatorId", "operator_id"),
            brand_name=str(_first("brandName", "brand_name") or "").strip() or None,
            only_first=_first("onlyFirst", "only_first"),
            task_metadata=metadata,
        )


class OutreachChatbotDispatcherService(ChatbotDispatcherService):
    """Open chat page, collect contact info, decide send, and update progress."""

    def __init__(self, *, account_name: Optional[str] = None) -> None:
        super().__init__()
        self.settings = get_settings()
        self.logger = logger
        if account_name:
            self.account_name = account_name

        self.task_metadata: Dict[str, Any] = {}
        self.brand_name = ""
        self.only_first = 0
        self.first_message_text = ""
        self.later_message_text = ""

        inner_api_token = getattr(self.settings, "INNER_API_AUTH_TOKEN", None)
        if not inner_api_token:
            valid_tokens = getattr(self.settings, "INNER_API_AUTH_VALID_TOKENS", []) or []
            inner_api_token = valid_tokens[0] if valid_tokens else None

        self.creator_history_client = CreatorHistoryClient(
            base_url=self.settings.INNER_API_BASE_URL,
            history_path=self.settings.INNER_API_CREATOR_HISTORY_PATH,
            header_name=self.settings.INNER_API_AUTH_REQUIRED_HEADER,
            token=inner_api_token,
            timeout=float(self.settings.INNER_API_TIMEOUT),
        )
        self.ingestion_client = CreatorIngestionClient(
            base_url=self.settings.INNER_API_BASE_URL,
            creator_path=self.settings.INNER_API_CREATOR_PATH,
            header_name=self.settings.INNER_API_AUTH_REQUIRED_HEADER,
            token=inner_api_token,
            timeout=float(self.settings.INNER_API_TIMEOUT),
        )
        self.outreach_task_client = OutreachTaskClient(
            base_url=self.settings.INNER_API_BASE_URL,
            task_path=self.settings.INNER_API_OUTREACH_TASK_PATH,
            progress_path=self.settings.INNER_API_OUTREACH_PROGRESS_PATH,
            header_name=self.settings.INNER_API_AUTH_REQUIRED_HEADER,
            token=inner_api_token,
            timeout=float(self.settings.INNER_API_TIMEOUT),
        )

    async def dispatch(self, task: OutreachChatbotTask) -> None:
        async with self._dispatch_lock:
            region = task.region or self.default_region
            self._apply_task_metadata(task)

            await self._ensure_browser(region, task.account_name or self.account_name)
            partner_id = str(
                getattr(getattr(self._runner, "account_profile", None), "creator_id", "")
                or ""
            )

            page = await self._runner.ensure_main_page()
            try:
                page = await self._navigate_to_chat_page(
                    page,
                    partner_id=partner_id,
                    creator_id=task.platform_creator_id,
                    region=region,
                )
                if not page:
                    raise MessageProcessingError("Failed to open chat page")

                connect, reply = await self._check_connection_status(page)

                message_type, message_text = await self._should_send_message(
                    creator_name=task.creator_name or task.platform_creator_display_name,
                    creator_id=task.platform_creator_id,
                    creator_username=task.platform_creator_username or task.creator_username,
                    actual_connect=connect,
                    actual_reply=reply,
                )

                send_ok = False
                if message_text:
                    send_ok = await self._send_single_message(
                        page, message_text, task.platform_creator_id
                    )
                else:
                    self.logger.warning(
                        "Message text empty; skip sending",
                        creator_id=task.platform_creator_id,
                        message_type=message_type,
                    )

                await self._send_product_lists(page)

                whatsapp, email = await self._extract_contact_info(page)
                await self._update_progress(task)

                await self._sync_creator_snapshot(
                    task=task,
                    connect=connect,
                    reply=reply,
                    whatsapp=whatsapp,
                    email=email,
                    send_ok=send_ok,
                    message_type=message_type,
                    chat_url=str(page.url or ""),
                    region=region,
                )
            except PlaywrightError:
                raise
            except Exception as exc:
                self.logger.error(
                    "Outreach dispatch failed",
                    task_id=task.task_id,
                    creator_id=task.platform_creator_id,
                    error=str(exc),
                    exc_info=True,
                )
                raise MessageProcessingError("Outreach dispatch failed") from exc
            finally:
                await self._return_to_home(page, region)

    async def close(self) -> None:
        await super().close()
        await self.creator_history_client.aclose()
        await self.ingestion_client.aclose()
        await self.outreach_task_client.aclose()

    async def _send_single_message(
        self, page, message: str, creator_id: str
    ) -> bool:
        if not message:
            return False

        input_waited = False
        for attempt in range(1, 4):
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
                    return False
                return False
            await self._click_send_button_if_present(page)
            sent = await self._verify_message_sent(page, baseline)
            if not sent and await self._chat_input_cleared(page):
                self.logger.info(
                    "Message likely sent (input cleared)",
                    creator_id=creator_id,
                )
                return True
            if not sent:
                try:
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(500)
                except Exception:
                    pass
                sent = await self._verify_message_sent(page, baseline)
            if sent:
                self.logger.info(
                    "Outreach message sent",
                    creator_id=creator_id,
                )
                return True
            self.logger.warning(
                "Outreach message verification failed",
                attempt=attempt,
                creator_id=creator_id,
            )
            await page.wait_for_timeout(1500)
        return False

    async def _chat_input_cleared(self, page) -> bool:
        try:
            return await page.evaluate(
                """() => {
                    const selectors = [
                        'textarea[placeholder="Send a message"]',
                        'textarea[placeholder*="Send a message"]',
                        'textarea[placeholder*="message" i]',
                        'textarea',
                        'div[contenteditable="true"][role="textbox"]',
                        'div[contenteditable="true"]',
                    ];
                    for (const selector of selectors) {
                        const el = document.querySelector(selector);
                        if (!el) continue;
                        if (el.tagName.toLowerCase() === "textarea") {
                            return !el.value || !el.value.trim();
                        }
                        if (el.isContentEditable) {
                            return !(el.textContent || "").trim();
                        }
                    }
                    return false;
                }"""
            )
        except Exception:
            return False

    async def _send_product_lists(self, page) -> None:
        products = self._parse_product_list()
        if not products:
            return

        try:
            tab = page.locator("#arco-tabs-0-tab-1").first
            if await tab.count() == 0:
                self.logger.warning("Product list tab not found; skipping")
                return
            await tab.click()
            await page.wait_for_timeout(1000)
        except Exception as exc:
            self.logger.warning("Failed to open product list tab", error=str(exc))
            return

        input_locator = page.locator('input[data-tid="m4b_input_search"]').first
        send_button = page.locator(
            'div[data-e2e="a92dd902-97bc-0527"] button[data-tid="m4b_button"]'
        ).first

        for product in products:
            try:
                await input_locator.wait_for(state="visible", timeout=5000)
                await input_locator.fill(product)
                await input_locator.press("Enter")
                await send_button.wait_for(state="visible", timeout=5000)
                await send_button.click()
                await page.wait_for_timeout(500)
                await input_locator.fill("")
            except Exception as exc:
                self.logger.warning(
                    "Failed to send product list item",
                    product=product,
                    error=str(exc),
                )

        try:
            profile_tab = page.locator("#arco-tabs-0-tab-0").first
            if await profile_tab.count() > 0:
                await profile_tab.click()
                await page.wait_for_timeout(1000)
        except Exception:
            self.logger.warning("Failed to return to profile tab", exc_info=True)

    def _parse_product_list(self) -> List[str]:
        metadata = self.task_metadata or {}
        raw = metadata.get("product_list") or metadata.get("productList") or ""
        if not raw:
            return []
        if isinstance(raw, (list, tuple)):
            items = [str(item).strip() for item in raw if str(item).strip()]
        else:
            items = [item.strip() for item in str(raw).split(",") if item.strip()]
        return items

    async def _check_connection_status(self, page) -> Tuple[bool, bool]:
        self.logger.info("Checking connection status in chat")
        try:
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(3000)

            chat_container = await page.evaluate(
                """
                () => {
                    const selectors = [
                        'div.index-module__messageList--GBz6X',
                        'div.messageList-k_OG24',
                        'div.chatd-scrollView',
                        'div[class*="messageList"]',
                        'div[class*="chatd-scrollView"]'
                    ];
                    for (const selector of selectors) {
                        const container = document.querySelector(selector);
                        if (container && container.offsetParent !== null) {
                            return selector;
                        }
                    }
                    return null;
                }
                """
            )
            if not chat_container:
                self.logger.warning("Chat container not found")
                return False, False

            messages = await page.evaluate(
                """
                (selector) => {
                    const container = document.querySelector(selector);
                    if (!container) return [];
                    const msgNodes = container.querySelectorAll('div.chatd-message');
                    const results = [];
                    msgNodes.forEach((msgNode) => {
                        const isRight = msgNode.className.includes('chatd-message--right');
                        const isLeft = msgNode.className.includes('chatd-message--left');
                        const contentEl = msgNode.querySelector('pre.index-module__content--QKRoB');
                        const content = contentEl ? contentEl.textContent.trim() : '';
                        if (!content || content.startsWith('im_sdk') || content.length < 2) return;
                        results.push({
                            content: content,
                            isFromMerchant: isRight,
                            isFromCreator: isLeft
                        });
                    });
                    return results;
                }
                """,
                chat_container,
            )

            if not isinstance(messages, list):
                messages = []

            connect = len(messages) > 0
            reply = any(item.get("isFromCreator", False) for item in messages)
            self.logger.info(
                "Chat connection status",
                message_count=len(messages),
                connect=connect,
                reply=reply,
            )
            return connect, reply
        except Exception as exc:
            self.logger.warning("Failed to check chat status", error=str(exc))
            return False, False

    async def _extract_contact_info(self, page) -> Tuple[str, str]:
        self.logger.info("Extracting contact info from chat page")
        whatsapp = ""
        email = ""
        start = asyncio.get_running_loop().time()
        max_seconds = 15

        try:
            profile_tab = page.locator("#arco-tabs-0-tab-0").first
            if await profile_tab.count() > 0:
                selected = await profile_tab.get_attribute("aria-selected")
                if selected != "true":
                    await profile_tab.click()
                    await page.wait_for_timeout(500)
            else:
                fallback_tab = page.locator('div[role="tab"]:has-text("Profile")').first
                if await fallback_tab.count() > 0:
                    selected = await fallback_tab.get_attribute("aria-selected")
                    if selected != "true":
                        await fallback_tab.click()
                        await page.wait_for_timeout(500)
        except Exception as exc:
            self.logger.info("Failed to activate profile tab", error=str(exc))

        contact_button_xpath = '//*[@id="arco-tabs-0-panel-0"]/div/div/div[1]/button'
        try:
            button = page.locator(f"xpath={contact_button_xpath}").first
            if await button.count() == 0:
                self.logger.info("Contact info button not found")
                return whatsapp, email
            await button.wait_for(state="visible", timeout=2000)
            await button.click()
            await page.wait_for_timeout(1000)
        except Exception as exc:
            self.logger.info("Failed to click contact info button", error=str(exc))
            return whatsapp, email

        if asyncio.get_running_loop().time() - start > max_seconds:
            self.logger.warning("Contact info timeout after opening dialog")
            return whatsapp, email

        try:
            unavailable_locator = page.locator(
                "text=This creator doesn't have contact information available."
            )
            await unavailable_locator.wait_for(state="visible", timeout=2000)
            if await unavailable_locator.count() > 0:
                self.logger.info("Contact info unavailable")
                for xpath in [
                    '/html/body/div[4]/div[2]/div/div[2]/div[3]/div/button',
                    '/html/body/div[3]/div[2]/div/div[2]/span',
                ]:
                    try:
                        close_btn = page.locator(f"xpath={xpath}").first
                        if await close_btn.count() > 0:
                            await close_btn.click()
                            await page.wait_for_timeout(500)
                    except Exception:
                        continue
                return whatsapp, email
        except Exception:
            pass

        base_xpath = "/html/body/div[3]/div[2]/div/div[2]/div[2]/div"
        for idx in range(2, 4):
            if asyncio.get_running_loop().time() - start > max_seconds:
                self.logger.warning("Contact info extraction timed out")
                break
            try:
                label_el = page.locator(f"xpath={base_xpath}/div[{idx}]/span").first
                if await label_el.count() == 0:
                    continue
                label_text = await label_el.text_content()
                if not label_text or not label_text.strip():
                    continue
                value_el = page.locator(
                    f"xpath={base_xpath}/div[{idx}]/div/div/span"
                ).first
                if await value_el.count() == 0:
                    continue
                value_text = await value_el.text_content()
                if not value_text or not value_text.strip():
                    continue

                label_lower = label_text.lower()
                if "whatsapp" in label_lower:
                    whatsapp = value_text.strip()
                elif "email" in label_lower or "e-mail" in label_lower:
                    email = value_text.strip()
            except Exception:
                continue

        try:
            close_btn = page.locator("xpath=/html/body/div[3]/div[2]/div/div[2]/span").first
            if await close_btn.count() > 0:
                await close_btn.click(timeout=1000)
                await page.wait_for_timeout(300)
        except Exception:
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(300)
            except Exception:
                pass

        return whatsapp, email

    async def _fetch_creator_history(
        self,
        *,
        creator_name: Optional[str],
        creator_id: Optional[str],
        creator_username: Optional[str],
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        try:
            return await self.creator_history_client.fetch(
                creator_id=creator_id,
                creator_name=creator_name,
                creator_username=creator_username,
                limit=limit,
            )
        except Exception as exc:
            self.logger.warning("Failed to load creator history", error=str(exc))
            return []

    async def _should_send_message(
        self,
        *,
        creator_name: Optional[str],
        creator_id: Optional[str],
        creator_username: Optional[str],
        actual_connect: bool,
        actual_reply: bool,
    ) -> Tuple[Optional[str], Optional[str]]:
        records = await self._fetch_creator_history(
            creator_name=creator_name,
            creator_id=creator_id,
            creator_username=creator_username,
        )

        if self.only_first == 2:
            if not records and not actual_connect:
                self.logger.info("%s: only_first=2 and new creator -> skip", creator_name)
                return None, None
            has_reply_history = any(r.get("reply", False) for r in records) or actual_reply
            if has_reply_history:
                self.logger.info("%s: reply history exists -> skip", creator_name)
                return None, None
            self.logger.info("%s: only_first=2 -> later", creator_name)
            return "later", (self.later_message_text or None)

        has_any_reply = any(r.get("reply", False) for r in records) or actual_reply
        if has_any_reply:
            self.logger.info("%s: reply history exists -> skip", creator_name)
            return None, None

        if len(records) >= 5 and all(not r.get("reply", False) for r in records):
            self.logger.info("%s: >=5 records with no reply -> skip", creator_name)
            return None, None

        if not records and not actual_connect:
            self.logger.info("%s: new creator -> first", creator_name)
            return "first", (self.first_message_text or None)

        if records and all(not r.get("connect", False) for r in records) and not actual_connect:
            self.logger.info("%s: all records not connected -> first", creator_name)
            return "first", (self.first_message_text or None)

        has_connected = any(r.get("connect", False) for r in records) or actual_connect
        if has_connected:
            if self.only_first == 1:
                self.logger.info("%s: connected and only_first=1 -> skip", creator_name)
                return None, None
            brand_names = {r.get("brand_name") for r in records if r.get("brand_name")}
            if not self.brand_name or self.brand_name not in brand_names:
                self.logger.info("%s: connected but brand differs -> later", creator_name)
                return "later", (self.later_message_text or self.first_message_text or None)
            self.logger.info("%s: connected and brand already exists -> skip", creator_name)
            return None, None

        return None, None

    def _apply_task_metadata(self, task: OutreachChatbotTask) -> None:
        metadata = dict(task.task_metadata or {})
        for key in (
            "task_name",
            "campaign_id",
            "campaign_name",
            "platform_campaign_id",
            "platform_campaign_name",
            "product_id",
            "product_name",
            "platform_product_id",
            "platform_product_name",
            "run_at_time",
            "run_end_time",
            "target_new_creators",
            "max_creators",
            "message",
            "task_type",
            "brand",
            "brand_name",
            "only_first",
            "email_first",
            "email_later",
            "email_first_body",
            "email_later_body",
            "search_strategy",
        ):
            value = getattr(task, key, None)
            if value is not None and key not in metadata:
                metadata[key] = value

        if task.only_first is not None:
            metadata["only_first"] = task.only_first
        if task.brand_name:
            metadata["brand_name"] = task.brand_name

        self.task_metadata = metadata

        brand_name = metadata.get("brand_name")
        if not brand_name and isinstance(metadata.get("brand"), dict):
            brand_name = metadata.get("brand", {}).get("name")
        self.brand_name = str(brand_name).strip() if brand_name else ""

        self._load_message_templates()

    def _format_message_text(self, subject: str, body: str) -> str:
        subject_clean = (subject or "").replace('"', "").strip()
        body_clean = (body or "").replace("\r\n", "\n")
        body_clean = re.sub(r"\n{3,}", "\n\n", body_clean).strip()
        if subject_clean and body_clean:
            return f"{subject_clean}\n\n{body_clean}"
        return subject_clean or body_clean

    def _load_message_templates(self) -> None:
        metadata = self.task_metadata or {}
        brand_meta = metadata.get("brand") if isinstance(metadata.get("brand"), dict) else {}
        only_first = metadata.get("only_first", brand_meta.get("only_first", 0))
        try:
            self.only_first = int(only_first)
        except (TypeError, ValueError):
            self.only_first = 0

        email_first = metadata.get("email_first") or {}
        if isinstance(email_first, str):
            self.first_message_text = email_first.strip()
        elif isinstance(email_first, dict):
            self.first_message_text = self._format_message_text(
                str(email_first.get("subject") or ""),
                str(email_first.get("email_body") or email_first.get("body") or ""),
            )
        else:
            self.first_message_text = str(metadata.get("email_first_body") or "").strip()

        email_later = metadata.get("email_later") or {}
        if isinstance(email_later, str):
            self.later_message_text = email_later.strip()
        elif isinstance(email_later, dict):
            self.later_message_text = self._format_message_text(
                str(email_later.get("subject") or ""),
                str(email_later.get("email_body") or email_later.get("body") or ""),
            )
        else:
            self.later_message_text = str(metadata.get("email_later_body") or "").strip()

    async def _update_progress(self, task: OutreachChatbotTask) -> None:
        if not task.outreach_task_id:
            return
        try:
            await self.outreach_task_client.increment_progress(
                task_id=task.outreach_task_id,
                delta=1,
                operator_id=task.operator_id or task.outreach_task_id,
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to update outreach progress",
                task_id=task.outreach_task_id,
                error=str(exc),
            )

    async def _sync_creator_snapshot(
        self,
        *,
        task: OutreachChatbotTask,
        connect: bool,
        reply: bool,
        whatsapp: str,
        email: str,
        send_ok: bool,
        message_type: Optional[str],
        chat_url: str,
        region: str,
    ) -> None:
        send_time = ""
        if send_ok:
            send_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        row = {
            "platform_creator_id": task.platform_creator_id,
            "platform_creator_username": task.platform_creator_username or task.creator_username,
            "platform_creator_display_name": task.platform_creator_display_name or task.creator_name,
            "creator_name": task.creator_name,
            "creator_username": task.creator_username,
            "creator_chaturl": chat_url,
            "whatsapp": whatsapp,
            "email": email,
            "connect": connect,
            "reply": reply,
            "send": send_ok,
            "send_time": send_time,
            "brand_name": self.brand_name,
            "region": region,
            "message_type": message_type,
        }
        options = {
            "task_id": task.outreach_task_id,
            "account_name": task.account_name or self.account_name,
            "region": region,
            "brand_name": self.brand_name,
            "search_strategy": (self.task_metadata or {}).get("search_strategy"),
        }
        try:
            await self.ingestion_client.submit(
                source="outreach_chatbot",
                operator_id=task.operator_id or task.outreach_task_id or task.task_id,
                options=options,
                rows=[row],
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to sync creator snapshot",
                creator_id=task.platform_creator_id,
                error=str(exc),
            )
