"""Full-featured TikTok sample crawler integrated with RabbitMQ consumer."""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple, Union

import pandas as pd
from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    Response,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from common.core.config import get_settings
from common.core.exceptions import MessageProcessingError, NonRetryableMessageError, PlaywrightError
from common.core.logger import get_logger
from .email_verifier import GmailVerificationCode
from .login_manager import LoginManager
from .sample_ingestion_client import SampleIngestionClient

settings = get_settings()
logger = get_logger()

@dataclass
class AccountProfile:
    """Account credentials loaded from config file."""

    name: str
    login_email: str
    login_password: Optional[str]
    gmail_username: str
    gmail_app_password: str
    region: str
    creator_id: Optional[str] = None
    enabled: bool = True


@dataclass
class CrawlOptions:
    """Runtime crawl options provided via MQ message."""

    campaign_id: Optional[str]
    campaign_ids: List[str]
    account_name: Optional[str]
    region: str
    tabs: List[str]
    expand_view_content: bool
    max_pages: Optional[int]
    scan_all_pages: bool
    export_excel: bool
    view_logistics: bool
    manual_login: bool


def _sanitize_numeric(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip().lower().replace(",", "")
    if not text:
        return None
    multiplier = 1
    if text.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000
        text = text[:-1]
    match = re.search(r"[-+]?\d*\.?\d+", text)
    if not match:
        return None
    try:
        numeric = float(match.group()) * multiplier
        return int(numeric)
    except ValueError:
        return None


def _sanitize_decimal(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (ValueError, InvalidOperation):
        try:
            # 兼容金额/截断展示，例如 "$157.93 ..." / "p... 1351.57"
            match = re.search(r"[-+]?\d*\.?\d+", text)
            if match:
                return Decimal(match.group())
            cleaned = re.sub(r"[^\d.]", "", text)
            match = re.search(r"[-+]?\d*\.?\d+", cleaned)
            return Decimal(match.group()) if match else None
        except (ValueError, InvalidOperation):
            return None


def _sanitize_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    lowered = str(value).strip().lower()
    if not lowered:
        return None
    if lowered in {"yes", "true", "1"} or "yes" in lowered:
        return True
    if lowered in {"no", "false", "0"} or "no" in lowered:
        return False
    return None


def _format_identifier(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return str(int(text))
    return text


def _sanitize_request_time(value: Optional[str]) -> Optional[str]:
    if value is None:
        return "--"
    text = str(value).strip().lower()
    if not text:
        return "--"
    if text.endswith("days"):
        number = text.replace("days", "").strip()
        return f"{number} days" if number.isdigit() else text
    if text.endswith("hours"):
        number = text.replace("hours", "").strip()
        return f"{number} hours" if number.isdigit() else text
    return text


def _format_order_expired_time(value: Any) -> str:
    if value is None:
        return "--"
    try:
        raw = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return "--"
    if raw < 0:
        raw = 0
    # TikTok 接口里该字段有时以秒返回，有时以毫秒返回；这里做一个保守的自适应：
    # - 小于 10_000_000（~115 天的秒数）时按“秒”处理（常见为几天内的秒数）
    # - 否则按“毫秒”处理
    seconds = raw // 1000 if raw >= 10_000_000 else raw
    days = seconds // (3600 * 24)
    if days >= 1:
        return f"{days} days"
    hours = seconds // 3600
    return f"{hours} hours"


def _clean_promotion_earn_text(value: Optional[str]) -> str:
    """兼容 UI 截断（例如 p... / p…）以及多余空白。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # 旧版页面会出现类似 `p... 1351.57` 的截断前缀
    text = re.sub(r"(?i)\bp(\.\.\.|…)\s*", "", text).strip()
    # 有些情况下会出现在中间，尽量清掉
    text = text.replace("p...", "").replace("p…", "").strip()
    return text


def _sanitize_post_rate_value(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    matches = re.findall(r"[-+]?\d*\.?\d+", str(value))
    if not matches:
        return None
    dec = _sanitize_decimal(matches[0])
    if dec is None:
        return None
    try:
        dec = dec.quantize(Decimal("0.01"))
    except Exception:
        pass
    return dec


def _extract_numeric_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    matches = re.findall(r"[-+]?\d*\.?\d+", str(value))
    if not matches:
        return None
    return matches[0]


class CrawlerRunnerService:
    """Asynchronous crawler that re-implements the historical sample_all logic."""

    def __init__(self, login_manager: Optional[LoginManager] = None) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._main_page: Optional[Page] = None
        self._tab_snapshot: Dict[str, int] = {}
        self._initialize_lock = asyncio.Lock()
        self._view_content_counter = 0
        self._task_deadline: Optional[float] = None
        # 样品列表分页（table pagination）当前页号：用于卡死/刷新后的恢复。
        self._table_page_index = 1
        # 如需避免任务时新开窗口，可通过配置 SAMPLE_REUSE_MAIN_PAGE=True 复用预热主页面
        self.reuse_main_page_for_tasks = bool(
            getattr(settings, "SAMPLE_REUSE_MAIN_PAGE", True)
        )
        # 任务级停止标记，可由上层请求终止当前任务
        self.stop_event = asyncio.Event()
        self.service_name = getattr(settings, "CONSUMER", "portal_tiktok_sample_crawler") or "portal_tiktok_sample_crawler"
        inner_api_token = (
            getattr(settings, "INNER_API_AUTH_TOKEN", None)
            or (
                settings.INNER_API_AUTH_VALID_TOKENS[0]
                if getattr(settings, "INNER_API_AUTH_VALID_TOKENS", [])
                else None
            )
        )
        self.ingestion_client = SampleIngestionClient(
            base_url=settings.INNER_API_BASE_URL,
            sample_path=settings.INNER_API_SAMPLE_PATH,
            header_name=settings.INNER_API_AUTH_REQUIRED_HEADER,
            token=inner_api_token,
            timeout=float(settings.INNER_API_TIMEOUT),
        )

        self.target_url = getattr(
            settings,
            "SAMPLE_TARGET_URL",
            "https://partner.tiktokshop.com/affiliate-campaign/sample-requests?tab=to_review",
        )
        self.default_tab_slug = self._extract_tab_slug(self.target_url) or "to_review"
        self.login_url = getattr(
            settings,
            "SAMPLE_LOGIN_URL",
            "https://partner-sso.tiktok.com/account/login?from=ttspc_logout&redirectURL=%2F%2Fpartner.tiktokshop.com%2Fhome&lang=en",
        )
        self.search_input_selector = getattr(
            settings,
            "SAMPLE_SEARCH_INPUT_SELECTOR",
            'input[data-tid="m4b_input_search"]',
        )
        self.default_region = getattr(settings, "SAMPLE_DEFAULT_REGION", "MX")
        self.operator_id = getattr(
            settings,
            "SAMPLE_DEFAULT_OPERATOR_ID",
            "00000000-0000-0000-0000-000000000000",
        )
        logger.info(f"PLAYWRIGHT_HEADLESS {settings.PLAYWRIGHT_HEADLESS}")
        self.headless = bool(getattr(settings, "PLAYWRIGHT_HEADLESS", True))
        self.account_config_path = getattr(
            settings, "SAMPLE_ACCOUNT_CONFIG_PATH", "configs/accounts.json"
        )
        self.accounts_data = self._load_accounts_config()
        self.default_region = getattr(settings, "SAMPLE_DEFAULT_REGION", "MX")
        self.default_tab = getattr(settings, "SAMPLE_DEFAULT_TAB", "all").lower()
        self.expand_view_content_default = bool(
            getattr(settings, "SAMPLE_EXPAND_VIEW_CONTENT", True)
        )
        self.export_excel_enabled = bool(
            getattr(settings, "SAMPLE_ENABLE_EXCEL_EXPORT", False)
        )
        self.view_logistics_default = bool(
            getattr(settings, "SAMPLE_VIEW_LOGISTICS_ENABLED", False)
        )
        # 性能/节奏控制（默认偏保守，可通过环境变量覆盖）
        self.search_settle_wait_ms = int(getattr(settings, "SAMPLE_SEARCH_SETTLE_WAIT_MS", 1200) or 1200)
        self.view_content_open_timeout_ms = int(getattr(settings, "SAMPLE_VIEW_CONTENT_OPEN_TIMEOUT_MS", 6000) or 6000)
        self.view_content_tab_settle_ms = int(getattr(settings, "SAMPLE_VIEW_CONTENT_TAB_SETTLE_MS", 250) or 250)
        # View content 抽屉里的 tab（video/live）可能是“渐进渲染”的：先出现一个 tab，再延迟出现第二个。
        # 为了避免只抓到默认打开的 LIVE 而漏抓 Video，这里给出一个“二次 tab 出现等待窗口”（毫秒）。
        self.view_content_tabs_grace_ms = int(getattr(settings, "SAMPLE_VIEW_CONTENT_TABS_GRACE_MS", 5500) or 5500)
        # View content 抽屉的“单 tab 处理/切换”与“总耗时”上限（毫秒）
        self.view_content_tab_timeout_ms = int(
            getattr(settings, "SAMPLE_VIEW_CONTENT_TAB_TIMEOUT_MS", 8000) or 8000
        )
        self.view_content_total_timeout_ms = int(
            getattr(settings, "SAMPLE_VIEW_CONTENT_TOTAL_TIMEOUT_MS", 20000) or 20000
        )
        # 分页卡死后的恢复策略（刷新后从第 1 页逐页点回目标页）
        self.table_page_recover_max_attempts = int(
            getattr(settings, "SAMPLE_TABLE_PAGE_RECOVER_MAX_ATTEMPTS", 5) or 5
        )
        self.table_page_recover_reload_timeout_ms = int(
            getattr(settings, "SAMPLE_TABLE_PAGE_RECOVER_RELOAD_TIMEOUT_MS", 60_000) or 60_000
        )
        # 单条消息（MQ task）最大运行时长（秒）。默认 12 小时。
        self.message_timeout_seconds = int(
            getattr(settings, "SAMPLE_MESSAGE_TIMEOUT_SECONDS", 12 * 60 * 60) or (12 * 60 * 60)
        )
        self.creator_detail_timeout_ms = int(getattr(settings, "SAMPLE_CREATOR_DETAIL_TIMEOUT_MS", 8000) or 8000)
        self.creator_detail_retry_sleep_ms = int(getattr(settings, "SAMPLE_CREATOR_DETAIL_RETRY_SLEEP_MS", 400) or 400)
        self.export_dir = Path(
            getattr(
                settings,
                "SAMPLE_EXPORT_DIR",
                Path("data/manage_sample"),
            )
        )
        self.tab_definitions: Dict[str, Dict[str, str]] = {
            "all": {"display": "All", "slug": "all"},
            "review": {"display": "To review", "slug": "to_review"},
            "ready": {"display": "Ready to ship", "slug": "ready_to_ship"},
            "shipped": {"display": "Shipped", "slug": "shipped"},
            "pending": {"display": "Content pending", "slug": "content_pending"},
            "completed": {"display": "Completed", "slug": "completed"},
            "canceled": {"display": "Canceled", "slug": "cancel"},
        }
        self.tab_mapping = {key: meta["display"] for key, meta in self.tab_definitions.items()}
        self.tab_slug_lookup: Dict[str, str] = {}
        self.tab_key_lookup: Dict[str, str] = {}
        for key, meta in self.tab_definitions.items():
            slug = meta["slug"]
            display = meta["display"]
            for alias in {key, display.lower(), slug}:
                self.tab_slug_lookup[alias] = slug
                self.tab_key_lookup[alias] = key
        self.iterable_tab_keys: List[str] = ["review", "ready", "shipped", "pending", "completed", "canceled"]
        manual_login_default = getattr(settings, "CHATBOT_MANUAL_LOGIN", None)
        if manual_login_default is None:
            manual_login_default = getattr(settings, "SAMPLE_MANUAL_LOGIN", False)
        self.manual_login_default = bool(manual_login_default)
        manual_email_code_input = getattr(settings, "CHATBOT_MANUAL_EMAIL_CODE_INPUT", None)
        if manual_email_code_input is None:
            manual_email_code_input = getattr(settings, "SAMPLE_MANUAL_EMAIL_CODE_INPUT", False)
        manual_email_code_input_timeout = getattr(
            settings, "CHATBOT_MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS", None
        )
        if manual_email_code_input_timeout is None:
            manual_email_code_input_timeout = getattr(
                settings, "SAMPLE_MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS", 180
            )
        self.manual_email_code_input = bool(manual_email_code_input)
        self.manual_email_code_input_timeout_seconds = int(
            manual_email_code_input_timeout or 180
        )

        self.account_profile: Optional[AccountProfile] = self._select_account(
            region=self.default_region, account_name=None
        )
        self.gmail_verifier: Optional[GmailVerificationCode] = None
        self.login_manager: LoginManager = login_manager or LoginManager(
            login_url=self.login_url,
            search_input_selector=self.search_input_selector,
            manual_login_default=self.manual_login_default,
            manual_email_code_input=self.manual_email_code_input,
            manual_email_code_input_timeout_seconds=self.manual_email_code_input_timeout_seconds,
        )
        self._active_tab_name: Optional[str] = None
        self._active_tab_slug: Optional[str] = None
        self._latest_sample_records_payload: Optional[Dict[str, Any]] = None
        self._latest_sample_records_request_url: Optional[str] = None

    def resolve_profile(self, region: str, account_name: Optional[str]) -> AccountProfile:
        """Pick the account profile for the given region/account without launching a browser."""
        profile = self._select_account(region=region, account_name=account_name)
        if profile and profile.creator_id:
            self.operator_id = profile.creator_id
        return profile

    def matches_profile(self, region: str, account_name: Optional[str]) -> bool:
        desired_profile = self.resolve_profile(region, account_name)
        return bool(
            self.account_profile
            and desired_profile.login_email == self.account_profile.login_email
        )

    def has_live_session(self) -> bool:
        """判断会话是否仍可复用。

        Playwright driver/transport 断开时，Python 侧对象可能仍“非空”，但任何 locator/page 操作都会报
        `Connection closed while reading from the driver`；这里尽量提前识别这类失效会话。
        """
        if not (self._playwright and self._browser and self._context):
            return False
        try:
            return bool(self._browser.is_connected())
        except Exception:
            return False

    def describe_session_state(self) -> Dict[str, Any]:
        """提供可观测的会话状态，用于排查池复用问题。"""
        state: Dict[str, Any] = {
            "playwright": bool(self._playwright),
            "browser": bool(self._browser),
            "context": bool(self._context),
            "browser_connected": None,
        }
        if self._browser:
            try:
                state["browser_connected"] = bool(self._browser.is_connected())
            except Exception as exc:
                state["browser_connected"] = f"error:{exc}"
        return state

    def _is_driver_closed_error(self, exc: Exception) -> bool:
        text = str(exc) or ""
        needles = (
            "Connection closed while reading from the driver",
            "pipe closed by peer",
            "Target closed",
            "Browser has been closed",
            "Browser closed",
        )
        return any(needle in text for needle in needles)

    async def _reset_on_login_failure(self, reason: str, exc: Optional[Exception] = None) -> None:
        logger.warning("登录状态验证失败，重置 Playwright 会话", reason=reason, error=str(exc) if exc else None)
        try:
            await self.close()
        except Exception:
            logger.warning("重置 Playwright 会话失败", exc_info=True)

    async def ensure_ready(self, options: CrawlOptions) -> None:
        desired_profile = self._select_account(options.region, options.account_name)
        await self._ensure_profile_session(desired_profile)

    async def ensure_account_session(self, region: Optional[str], account_name: Optional[str]) -> None:
        """轻量封装，供其他服务只依赖登录态时复用。"""
        desired_profile = self._select_account(region or self.default_region, account_name)
        await self._ensure_profile_session(desired_profile)

    async def _ensure_profile_session(self, desired_profile: AccountProfile) -> None:
        if not self.has_live_session():
            raise PlaywrightError("Playwright 会话不存在或已被关闭，请通过池管理器重新创建")

        if self.account_profile and desired_profile.login_email != self.account_profile.login_email:
            raise PlaywrightError("当前浏览器登录账号与任务要求不一致")

        # 如果是第一次绑定 profile，则记录下来，后续只校验一致性
        if not self.account_profile:
            self.account_profile = desired_profile
        # 更新 operator_id 以在持久化时使用
        if desired_profile and desired_profile.creator_id:
            self.operator_id = desired_profile.creator_id

        # 确认登录态可用；使用现有浏览器重试登录而不是重建实例
        try:
            await self.ensure_main_page()
        except Exception as exc:
            await self._reset_on_login_failure("初始化主页面失败", exc)
            raise PlaywrightError("登录态检查失败，需要重建浏览器会话") from exc

        try:
            logged_in = await self.login_manager.is_logged_in(self._main_page)
        except Exception as exc:
            await self._reset_on_login_failure("登录状态检查异常", exc)
            raise PlaywrightError("登录态检查异常，需要重建浏览器会话") from exc

        if not logged_in:
            try:
                await self._perform_login(self._main_page)
                logged_in = await self.login_manager.is_logged_in(self._main_page)
            except Exception as exc:
                await self._reset_on_login_failure("登录失败或无法验证登录状态", exc)
                raise PlaywrightError("登录失败，需要重建浏览器会话") from exc

            if not logged_in:
                await self._reset_on_login_failure("登录后仍无法验证登录状态")
                raise PlaywrightError("登录状态无法验证，需要重建浏览器会话")

    async def ensure_main_page(self) -> Page:
        """确保 self._main_page 可用并返回它。"""
        context = self.get_browser_context()
        if not self._main_page or self._main_page.is_closed():
            self._main_page = await context.new_page()
        # 轻量健康检查：driver 断开时尽早失败，让外层池管理器重建会话，避免任务中途报 pipe/connection closed。
        try:
            await self._main_page.evaluate("1")
        except Exception as exc:
            if self._is_driver_closed_error(exc):
                try:
                    await self.close()
                except Exception:
                    pass
                raise PlaywrightError("Playwright driver connection closed; session needs rebuild") from exc
            raise
        return self._main_page

    def get_browser_context(self) -> BrowserContext:
        if not self._context:
            raise PlaywrightError("Playwright context is not ready")
        return self._context

    async def new_page(self) -> Page:
        """用于其他功能快速获取一个登陆后的 Page。"""
        context = self.get_browser_context()
        return await context.new_page()

    async def initialize(self, profile: Optional[AccountProfile] = None) -> None:
        target_profile = profile or self.account_profile
        if not target_profile or not target_profile.login_email:
            raise PlaywrightError("Account login email missing")
        if not target_profile.gmail_username or not target_profile.gmail_app_password:
            raise PlaywrightError("Gmail credentials missing for verification flow")

        try:
            logger.info("初始化 Playwright", HeaderLess=self.headless)

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(
                viewport={"width": 1600, "height": 900},
                ignore_https_errors=True,
            )
            self._context.set_default_timeout(60_000)
            self._main_page = await self._context.new_page()
            self.account_profile = target_profile
            if target_profile and target_profile.creator_id:
                self.operator_id = target_profile.creator_id
            self.gmail_verifier = GmailVerificationCode(
                username=target_profile.gmail_username,
                app_password=target_profile.gmail_app_password,
            )

            await self._perform_login(self._main_page)
        except Exception as exc:
            await self.close()
            raise PlaywrightError("Playwright initialization failed") from exc

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
        await self.ingestion_client.aclose()

    async def process_campaign_task(self, payload: Dict[str, Any]) -> None:
        logger.info("启动 sample crawler 任务", payload=payload)

        timeout_seconds = self._resolve_message_timeout_seconds(payload)
        self._task_deadline = time.monotonic() + timeout_seconds if timeout_seconds else None

        options = self._build_options(payload)
        await self.ensure_ready(options)
        assert self._context

        changed_tabs = await self._detect_tab_updates()
        if changed_tabs:
            logger.info("Detected tab counter updates: %s", changed_tabs)

        reuse_main = self.reuse_main_page_for_tasks
        crawler_page = self._main_page if reuse_main and self._main_page else await self._context.new_page()
        try:
            all_rows: List[Dict[str, Any]] = []
            if options.campaign_ids:
                campaign_ids = options.campaign_ids
            elif options.campaign_id:
                campaign_ids = [options.campaign_id]
            else:
                campaign_ids = [None]
            primary_tab_slug = self._tab_slug_for(options.tabs[0]) if options.tabs else None
            # 任务开始先统一跳转到样品页，避免停留在首页
            await self._goto_sample_dashboard(crawler_page, options.region, primary_tab_slug)
            if not self._tab_snapshot:
                await self._capture_tab_snapshot(crawler_page)
            for campaign_id in campaign_ids:
                if self._deadline_reached():
                    break
                for tab_name in options.tabs:
                    if self._deadline_reached():
                        break
                    tab_slug = self._tab_slug_for(tab_name)
                    try:
                        await self._goto_sample_dashboard(crawler_page, options.region, tab_slug)
                        await self._click_tab(crawler_page, tab_name)
                        if campaign_id:
                            await self._search_campaign(crawler_page, campaign_id)
                        else:
                            await self._clear_search(crawler_page)
                        # 等待表格刷新：避免固定 sleep 过长造成整体任务慢
                        await crawler_page.wait_for_timeout(self.search_settle_wait_ms)
                        total_pages = await self._determine_total_pages(crawler_page)
                        logger.info(
                            "准备爬取 Campaign %s, tab=%s, 检测到总页数=%s",
                            campaign_id or "(all)",
                            tab_name,
                            total_pages,
                        )
                        tab_rows = await self._crawl_pages(
                            crawler_page,
                            options,
                            campaign_id=campaign_id,
                            total_pages=total_pages,
                            tab_name=tab_name,
                        )
                        all_rows.extend(tab_rows)
                    except Exception:
                        logger.error("Tab crawl failed; skipping", exc_info=True, tab=tab_name, campaign_id=campaign_id)
                        continue
                # 清空搜索框，为下一个 campaign 做准备
                try:
                    await self._clear_search(crawler_page)
                except Exception:
                    pass

            if not all_rows and (options.campaign_id or options.campaign_ids):
                logger.info("未找到任何匹配的 Campaign 结果，任务完成")
                return
            if not all_rows:
                raise MessageProcessingError("No rows found for the requested task")
        except MessageProcessingError:
            logger.error("Campaign processing failed (non-retryable)", exc_info=True)
            return
        except Exception as exc:
            logger.error("Campaign processing failed", exc_info=True)
            return
        finally:
            # 注意：不要在任务中途异常时回到首页；由上层会话池释放阶段统一处理回首页。
            if not reuse_main:
                await crawler_page.close()
            self._task_deadline = None

    def _resolve_message_timeout_seconds(self, payload: Dict[str, Any]) -> int:
        raw_seconds = payload.get("message_timeout_seconds") or payload.get("max_runtime_seconds")
        if isinstance(raw_seconds, (int, float)) and raw_seconds > 0:
            return int(raw_seconds)
        raw_hours = payload.get("message_timeout_hours") or payload.get("max_runtime_hours")
        if isinstance(raw_hours, (int, float)) and raw_hours > 0:
            return int(raw_hours * 3600)
        return max(1, int(self.message_timeout_seconds))

    def _deadline_reached(self) -> bool:
        if self._task_deadline is None:
            return False
        if time.monotonic() < self._task_deadline:
            return False
        if not self.stop_event.is_set():
            self.stop_event.set()
            logger.warning("单条消息运行超时，停止继续爬取")
        return True

    async def _perform_login(self, page: Page) -> None:
        if not self.account_profile or not self.gmail_verifier:
            raise PlaywrightError("Account login context missing")
        await self.login_manager.perform_login(
            page=page,
            account_profile=self.account_profile,
            gmail_verifier=self.gmail_verifier,
            dump_debug_cb=self._dump_debug,
        )

    async def _wait_for_manual_login(self, page: Page, timeout: int = 300_000) -> None:
        await self.login_manager.wait_for_manual_login(page, timeout)

    def _tab_slug_for(self, tab_name: Optional[str]) -> Optional[str]:
        if not tab_name:
            return None
        return self.tab_slug_lookup.get(str(tab_name).strip().lower())

    def _apply_tab_query(self, url: str, tab_slug: Optional[str]) -> str:
        if not tab_slug:
            return url
        try:
            parsed = urlparse(url)
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query["tab"] = tab_slug
            encoded = urlencode(query, doseq=True)
            return urlunparse(parsed._replace(query=encoded))
        except Exception:
            return url

    def _extract_tab_slug(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        try:
            parsed = urlparse(url)
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            return query.get("tab")
        except Exception:
            return None

    def _target_url_for_region(self, region: Optional[str]) -> str:
        target = self.target_url
        region_code = (region or self.default_region or "").upper()
        if "partner.tiktokshop.com" in target and region_code.startswith("FR"):
            return target.replace("partner.tiktokshop.com", "partner.eu.tiktokshop.com")
        return target

    def _home_url_for_region(self, region: Optional[str]) -> str:
        region_code = (region or self.default_region or "").upper()
        if region_code.startswith("FR"):
            return "https://partner.eu.tiktokshop.com/home"
        return "https://partner.tiktokshop.com/home"

    async def _goto_sample_dashboard(self, page: Page, region: Optional[str] = None, tab_slug: Optional[str] = None) -> None:
        base_target = self._target_url_for_region(region)
        effective_tab = tab_slug or self._extract_tab_slug(base_target) or self.default_tab_slug
        target = self._apply_tab_query(base_target, effective_tab) if effective_tab else base_target
        if effective_tab:
            tab_key = self.tab_key_lookup.get(effective_tab, effective_tab)
            self._active_tab_slug = effective_tab
            self._active_tab_name = self.tab_mapping.get(tab_key, tab_key.title())
        current_url = page.url or ""
        current_slug = self._extract_tab_slug(current_url)
        is_sample_page = "sample-requests" in current_url
        if is_sample_page and (not effective_tab or current_slug == effective_tab):
            try:
                await page.wait_for_selector('text="Manage samples"', timeout=2_000)
                return
            except Exception:
                pass

        try:
            async with page.expect_response(
                lambda resp: self._is_partner_sample_records_url(resp.url),
                timeout=20_000,
            ) as resp_info:
                await page.goto(target, wait_until="networkidle", timeout=60_000)
            response = await resp_info.value
            await self._update_sample_records_context(response)
        except Exception:
            await page.goto(target, wait_until="networkidle", timeout=60_000)
        if not await self.login_manager.is_logged_in(page):
            await self._perform_login(page)
        # 等待页面稳定并确认已到样品页
        try:
            await page.wait_for_selector('text="Manage samples"', timeout=60_000)
        except Exception:
            # 最后兜底：如仍未看到标识，再跳转一次
            try:
                async with page.expect_response(
                    lambda resp: self._is_partner_sample_records_url(resp.url),
                    timeout=20_000,
                ) as resp_info:
                    await page.goto(target, wait_until="networkidle", timeout=60_000)
                response = await resp_info.value
                await self._update_sample_records_context(response)
            except Exception:
                await page.goto(target, wait_until="networkidle", timeout=60_000)
            await page.wait_for_selector('text="Manage samples"', timeout=60_000)

    def _is_partner_sample_records_url(self, url: str) -> bool:
        return (
            "/api/v1/affiliate/partner/sample/records/list" in url
            or "/sample/records/list" in url
        )

    def _is_partner_content_list_url(self, url: str) -> bool:
        return "/campaign/product/creator/content/list" in (url or "")

    async def _update_sample_records_context(self, response: Response) -> Dict[str, Any]:
        try:
            payload = await response.json()
        except Exception as exc:
            try:
                body = await response.text()
            except Exception:
                body = "<unreadable>"
            raise MessageProcessingError(
                f"Failed to decode sample records response: {exc} body={body[:500]}"
            ) from exc

        request_url = response.request.url if response.request else response.url
        self._latest_sample_records_payload = payload if isinstance(payload, dict) else None
        self._latest_sample_records_request_url = request_url
        return payload if isinstance(payload, dict) else {}

    def _extract_sample_records(self, payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not payload:
            return []
        records = payload.get("sample_records")
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]
        data = payload.get("data")
        if isinstance(data, dict):
            records = data.get("sample_records") or data.get("sampleRecords")
            if isinstance(records, list):
                return [record for record in records if isinstance(record, dict)]
        return []

    def _extract_content_list(
        self, payload: Optional[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Optional[int]]:
        if not payload:
            return [], None
        contents = payload.get("contents")
        total = payload.get("total")
        if isinstance(contents, list):
            cleaned = [item for item in contents if isinstance(item, dict)]
            return cleaned, int(total) if isinstance(total, (int, str)) and str(total).isdigit() else None
        data = payload.get("data")
        if isinstance(data, dict):
            contents = data.get("contents")
            total = data.get("total")
            if isinstance(contents, list):
                cleaned = [item for item in contents if isinstance(item, dict)]
                return cleaned, int(total) if isinstance(total, (int, str)) and str(total).isdigit() else None
        return [], None

    async def _ensure_sample_records_payload(self, page: Page) -> Dict[str, Any]:
        if isinstance(self._latest_sample_records_payload, dict):
            return self._latest_sample_records_payload
        try:
            async with page.expect_response(
                lambda resp: self._is_partner_sample_records_url(resp.url),
                timeout=30_000,
            ) as resp_info:
                await page.reload(wait_until="networkidle", timeout=60_000)
            response = await resp_info.value
            return await self._update_sample_records_context(response)
        except Exception as exc:
            raise MessageProcessingError(
                "Failed to capture sample records list; ensure the page is logged in and opened."
            ) from exc

    def _build_base_row_from_sample_record(
        self,
        record: Dict[str, Any],
        region: str,
        *,
        status_label: str = "",
    ) -> Dict[str, Any]:
        product_info = record.get("product_info") or {}
        creator_info = record.get("creator_info") or {}
        campaign_info = record.get("campaign_info") or {}

        creator_username = str(creator_info.get("user_name") or "").strip()
        creator_id = str(creator_info.get("id") or "").strip()
        creator_oec_id = str(creator_info.get("oec_id") or "").strip()
        platform_creator_id = creator_oec_id or creator_id
        extracted_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "region": region,
            "product_name": str(product_info.get("product_name") or "").strip(),
            "platform_product_id": str(product_info.get("product_id") or "").strip(),
            "platform_campaign_id": str(campaign_info.get("campaign_id") or "").strip(),
            "platform_campaign_name": str(campaign_info.get("name") or "").strip(),
            "product_sku": str(product_info.get("sku_info") or "").strip(),
            "stock": str(product_info.get("stock") or "").strip(),
            "available_sample_count": product_info.get("sample_quota"),
            "status": status_label or self._active_tab_name or "",
            "request_time_remaining": _format_order_expired_time(record.get("order_expired_time")),
            "creator_name": creator_username,
            "creator_username": creator_username,
            "creator_id": creator_id,
            "platform_creator_id": platform_creator_id,
            "post_rate": str(creator_info.get("post_rate") or "").strip(),
            "is_showcase": record.get("is_product_in_showcase"),
            "extracted_time": extracted_time,
        }


    async def _goto_home(self, page: Page, region: Optional[str] = None) -> None:
        home_url = self._home_url_for_region(region)
        try:
            await page.goto(home_url, wait_until="networkidle", timeout=30_000)
        except Exception:
            pass

        selectors = [
            self.search_input_selector,
            'input[placeholder="Search campaign ID"]',
            'input[data-tid="m4b_input_search"]',
            'text="Welcome to TikTok Shop Partner Center"',
            'text="Account GMV trend"',
            'text="View your data and facilitate seller authorizations"',
            'text="Hi"',
        ]
        last_error: Optional[Exception] = None
        for selector in selectors:
            try:
                await page.wait_for_selector(selector, timeout=60_000)
                return
            except Exception as exc:
                last_error = exc
                continue
        await self._dump_debug(page, "goto_sample_dashboard")
        if last_error:
            raise last_error

    async def _goto_home_soft(
        self,
        page: Page,
        region: Optional[str] = None,
        wait_ms: int = 5000,
    ) -> None:
        """释放阶段使用：尽量不依赖首页 DOM 结构判定，避免卡死在 wait_for_selector。"""
        home_url = self._home_url_for_region(region)
        try:
            await page.goto(home_url, wait_until="domcontentloaded", timeout=20_000)
        except Exception:
            pass
        try:
            await page.wait_for_timeout(wait_ms)
        except Exception:
            pass

    async def _clear_search(self, page: Page) -> None:
        try:
            search_input = page.locator(self.search_input_selector).first
            await search_input.fill("")
            try:
                async with page.expect_response(
                    lambda resp: self._is_partner_sample_records_url(resp.url),
                    timeout=15_000,
                ) as resp_info:
                    await search_input.press("Enter")
                response = await resp_info.value
                await self._update_sample_records_context(response)
            except PlaywrightTimeoutError:
                await search_input.press("Enter")
            await page.wait_for_timeout(1500)
        except Exception:
            pass

    async def _dump_debug(self, page: Page, prefix: str) -> None:
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        screenshot_path = logs_dir / f"{prefix}_{timestamp}.png"
        html_path = logs_dir / f"{prefix}_{timestamp}.html"
        try:
            await page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            screenshot_path = None
        try:
            html = await page.content()
            html_path.write_text(html, encoding="utf-8")
        except Exception:
            html_path = None
        logger.error(
            "Saved debug artifacts. url=%s screenshot=%s html=%s",
            page.url,
            screenshot_path,
            html_path,
        )

    async def _search_campaign(self, page: Page, campaign_id: str, wait_ms: int = 6000) -> None:
        for attempt in range(3):
            try:
                try:
                    await page.wait_for_selector(self.search_input_selector, timeout=30_000)
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1)
                    continue
                inputs = page.locator(self.search_input_selector)
                count = await inputs.count()
                search_input = inputs.nth(1) if count > 1 else inputs.first

                # 确认筛选条件是 Campaign ID
                try:
                    combobox = page.locator("div.m4b-input-group-select div[role='combobox']").first
                    if await combobox.count():
                        await combobox.click()
                        await page.get_by_text("Campaign ID").click()
                except Exception:
                    pass

                await search_input.fill("")
                await search_input.fill(campaign_id)
                try:
                    async with page.expect_response(
                        lambda resp: self._is_partner_sample_records_url(resp.url),
                        timeout=20_000,
                    ) as resp_info:
                        await search_input.press("Enter")
                        # 额外点击放大镜以确保触发搜索
                        try:
                            suffix = search_input.locator(
                                "xpath=ancestor::span[contains(@class,'arco-input-group')]"
                                "//span[contains(@class,'arco-input-group-suffix')]"
                            ).first
                            if await suffix.count():
                                await suffix.click()
                        except Exception:
                            pass
                    response = await resp_info.value
                    await self._update_sample_records_context(response)
                except PlaywrightTimeoutError:
                    await search_input.press("Enter")
                await page.wait_for_timeout(wait_ms)
                try:
                    await page.wait_for_selector("tbody tr", timeout=30_000)
                except Exception:
                    pass
                return
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(1)

    async def _determine_total_pages(self, page: Page) -> Optional[int]:
        try:
            items = page.locator("li.arco-pagination-item")
            count = await items.count()
            max_page = 0
            for idx in range(count):
                try:
                    text = (await items.nth(idx).inner_text()).strip()
                    if text.isdigit():
                        val = int(text)
                        max_page = max(max_page, val)
                except Exception:
                    continue
            return max_page or None
        except Exception:
            return None

    async def _get_current_table_page_index(self, page: Page) -> Optional[int]:
        try:
            active = page.locator("li.arco-pagination-item-active").first
            if not await active.count():
                active = page.locator("li.arco-pagination-item.arco-pagination-item-active").first
            if not await active.count():
                return None
            text = (await active.inner_text()).strip()
            return int(text) if text.isdigit() else None
        except Exception:
            return None

    async def _recover_table_pagination(
        self,
        page: Page,
        options: CrawlOptions,
        campaign_id: Optional[str],
        tab_name: str,
        *,
        target_page_index: int,
    ) -> bool:
        """分页卡死/点击无响应时的恢复：刷新页面 -> 回到第 1 页 -> 逐页点回目标页。"""
        target_page_index = max(1, int(target_page_index or 1))
        tab_slug = self._tab_slug_for(tab_name)

        for attempt in range(self.table_page_recover_max_attempts):
            if self.stop_event.is_set():
                raise MessageProcessingError("Task cancelled by request")

            logger.warning(
                "分页异常，尝试刷新并恢复到目标页",
                extra={
                    "recover_attempt": attempt + 1,
                    "recover_max": self.table_page_recover_max_attempts,
                    "target_page_index": target_page_index,
                    "tab_name": tab_name,
                },
            )

            # 刷新会导致 View content 的 arco-tabs 计数重置，因此也同步重置本地计数器
            self._view_content_counter = 0
            self._latest_sample_records_payload = None
            self._latest_sample_records_request_url = None

            try:
                await page.reload(wait_until="networkidle", timeout=self.table_page_recover_reload_timeout_ms)
            except Exception:
                # reload 失败时，走 goto_sample_dashboard 兜底
                pass

            try:
                await self._goto_sample_dashboard(page, options.region, tab_slug)
                await self._click_tab(page, tab_name)
                if campaign_id:
                    await self._search_campaign(page, str(campaign_id).strip())
                else:
                    await self._clear_search(page)
                await page.wait_for_timeout(self.search_settle_wait_ms)
            except Exception:
                logger.warning("刷新后恢复到样品页失败，重试中", exc_info=True)
                await asyncio.sleep(1)
                continue

            current_page = await self._get_current_table_page_index(page) or 1
            self._table_page_index = current_page
            if current_page != 1:
                logger.info("刷新后未回到第 1 页，将从当前页继续恢复", current_page=current_page)

            # 逐页点到目标页
            while current_page < target_page_index:
                if self.stop_event.is_set():
                    raise MessageProcessingError("Task cancelled by request")
                if not await self._has_next_page(page):
                    return False
                ok = await self._goto_next_page(page)
                if not ok:
                    break
                current_page += 1
                self._table_page_index = current_page

            if current_page == target_page_index:
                logger.info("已恢复到目标页", target_page_index=target_page_index, tab_name=tab_name)
                return True

            await asyncio.sleep(1)

        return False

    async def _crawl_pages(
        self,
        page: Page,
        options: CrawlOptions,
        campaign_id: Optional[str],
        total_pages: Optional[int],
        tab_name: str,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page_index = 1
        # 如果提供总页数，则严格按照该数量遍历，不再额外多翻页
        total_pages_limit = total_pages or None
        status_label = self.tab_mapping.get(tab_name.lower(), tab_name)
        detected_page = await self._get_current_table_page_index(page)
        if detected_page and detected_page > 0:
            page_index = detected_page
        self._table_page_index = page_index

        while True:
            if self.stop_event.is_set():
                break
            self._table_page_index = page_index
            page_rows = await self._crawl_current_page(
                page,
                options.region,
                options.expand_view_content,
                options.view_logistics,
                status_label=status_label,
            )
            if campaign_id:
                target = campaign_id.strip()
                page_rows = [
                    row
                    for row in page_rows
                    if target in (row.get("platform_campaign_id") or row.get("campaign_id") or "")
                ]
            # 每页抓取后即时持久化，减少长任务风险
            if page_rows:
                normalized = self._normalize_rows(page_rows)
                if normalized:
                    try:
                        await self._persist_results(normalized, options)
                    except Exception:
                        logger.error("Persist results failed; keep crawling", exc_info=True)
                    rows.extend(normalized)

            # 当存在 campaign_id 时，默认翻页直到结束或达到 max_pages
            if not campaign_id and not options.scan_all_pages:
                break

            if options.max_pages and page_index >= options.max_pages:
                break
            if total_pages_limit and page_index >= total_pages_limit:
                logger.info(
                    "已完成全部检测到的页数, 当前页=%s total=%s",
                    page_index,
                    total_pages_limit,
                )
                break

            if not await self._has_next_page(page):
                break
            next_target = page_index + 1
            moved = await self._goto_next_page(page)
            if not moved:
                recovered = await self._recover_table_pagination(
                    page,
                    options,
                    campaign_id,
                    tab_name,
                    target_page_index=next_target,
                )
                if not recovered:
                    break
                page_index = next_target
                continue
            page_index = next_target

        if options.export_excel and rows:
            await asyncio.to_thread(self._export_rows, rows, options)
        return rows

    async def _crawl_current_page(
            self,
            page: Page,
            region: str,
            expand_view_content: bool,
            view_logistics: bool,
            status_label: Optional[str],
    ) -> List[Dict[str, Any]]:
        if view_logistics:
            logger.warning(
                "portal_tiktok_sample_crawler 当前仅支持通过 Partner API 抓取样品列表/内容，暂不抓取 logistics"
            )

        payload = await self._ensure_sample_records_payload(page)
        sample_records = self._extract_sample_records(payload)
        if not sample_records:
            return []

        rows: List[Dict[str, Any]] = []
        row_locator: Optional[Locator] = None
        row_count = 0
        try:
            row_locator = page.locator("tbody").first.locator("tr")
            row_count = await row_locator.count()
        except Exception:
            row_locator = None

        for idx, record in enumerate(sample_records):
            if self.stop_event.is_set():
                break

            base_row = self._build_base_row_from_sample_record(
                record,
                region,
                status_label=status_label or self._active_tab_name or "",
            )
            if not base_row.get("platform_product_id"):
                continue

            row_element: Optional[Locator] = None
            if row_locator is not None and idx < row_count:
                row_element = row_locator.nth(idx)

            if expand_view_content and row_element:
                content_rows = await self._handle_view_content(
                    page,
                    row_element,
                    base_row,
                    expand_view_content,
                )
                if content_rows:
                    rows.extend(content_rows)
                else:
                    rows.append(self._empty_promotion_row(base_row))
            else:
                rows.append(self._empty_promotion_row(base_row))
        return rows

    async def _extract_row_data(self, row_element: Locator) -> Dict[str, Any]:
        data: Dict[str, Any] = {}

        async def safe_inner_text(locator: Locator) -> str:
            try:
                return (await locator.inner_text()).strip()
            except Exception:
                return ""

        data["product_name"] = await safe_inner_text(
            row_element.locator('span[style*="text-overflow: ellipsis"][style*="-webkit-line-clamp: 2"]').first
        )

        id_loc = row_element.locator('span.text-body-s-regular:has-text("ID:")')
        try:
            if await id_loc.count():
                product_id_text = await id_loc.nth(0).inner_text()
                data["platform_product_id"] = (
                    product_id_text.replace("ID:", "").strip()
                )
                if await id_loc.count() > 1:
                    campaign_id_text = await id_loc.nth(1).inner_text()
                    data["platform_campaign_id"] = campaign_id_text.replace("ID:", "").strip()
        except Exception:
            pass

        try:
            sku_parent = row_element.locator('span.text-neutral-text3:has-text("SKU:")').locator("..")
            data["product_sku"] = (await sku_parent.inner_text()).replace("SKU:", "").strip()
        except Exception:
            data["product_sku"] = ""

        try:
            stock_parent = row_element.locator('span.text-neutral-text3:has-text("Stock:")').locator("..")
            data["stock"] = (await stock_parent.inner_text()).replace("Stock:", "").strip()
        except Exception:
            data["stock"] = ""

        try:
            second_td = row_element.locator("td").nth(1)
            available_elem = second_td.locator('div[style*="width: fit-content"]').first
            data["available_sample_count"] = (await available_elem.inner_text()).strip()
        except Exception:
            data["available_sample_count"] = ""

        data["status"] = await safe_inner_text(row_element.locator(".arco-tag .text").first)

        try:
            time_remaining_cell = row_element.locator("td").nth(3)
            data["request_time_remaining"] = (await time_remaining_cell.inner_text()).strip()
        except Exception:
            data["request_time_remaining"] = ""

        try:
            post_rate_cell = row_element.locator("td").nth(6)
            data["post_rate"] = (await post_rate_cell.inner_text()).strip()
        except Exception:
            data["post_rate"] = ""

        try:
            # 该列在不同账号/页面版本里可能会变更列位置（例如在第 5 列出现 Yes/No）
            # 优先在整行里寻找明确的 Yes/No 文本，再回退到固定列索引。
            showcase_value = ""
            cells = row_element.locator("td")
            cell_count = await cells.count()
            for idx in range(cell_count):
                text = (await cells.nth(idx).inner_text()).strip()
                lowered = text.lower()
                if lowered in {"yes", "no"}:
                    showcase_value = text
                    break
            if not showcase_value:
                showcase_cell = row_element.locator("td").nth(10)
                showcase_value = (await showcase_cell.inner_text()).strip()
            data["is_showcase"] = showcase_value
        except Exception:
            data["is_showcase"] = ""

        data["platform_campaign_name"] = await safe_inner_text(
            row_element.locator(".arco-typography.m4b-typography-paragraph.text-body-m-regular").first
        )

        return data

    def _empty_promotion_row(self, base_row: Dict[str, Any]) -> Dict[str, Any]:
        row = base_row.copy()
        row.setdefault("creator_url", "")
        row.setdefault("type", "")
        row.setdefault("type_number", "")
        row.setdefault("promotion_name", "")
        row.setdefault("promotion_time", "")
        row.setdefault("promotion_view", "")
        row.setdefault("promotion_like", "")
        row.setdefault("promotion_comment", "")
        row.setdefault("promotion_order", "")
        row.setdefault("promotion_earn", "")
        row.setdefault("promotion_link", "")
        return row

    async def _get_creator_info(self, page: Page, row_element: Locator) -> Tuple[str, str, str]:
        fallback = ""
        try:
            creator_text_elem = row_element.locator(
                '.arco-typography.m4b-typography-text.sc-dcJsrY.gBlgCq'
            ).first
            if await creator_text_elem.count():
                fallback = (await creator_text_elem.inner_text()).strip()
        except Exception:
            fallback = ""

        detail_info = await self._fetch_creator_detail(page, row_element, fallback)
        if detail_info:
            return detail_info
        return fallback, "", ""

    async def _fetch_creator_detail(
            self, page: Page, row_element: Locator, fallback_name: str
    ) -> Optional[Tuple[str, str, str]]:
        avatar = await self._get_avatar_element(row_element)
        if avatar is None:
            return None

        for attempt in range(3):
            detail_page: Optional[Page] = None
            is_new_page = False
            try:
                try:
                    async with page.context.expect_page(timeout=10_000) as popup_info:
                        await avatar.click()
                    detail_page = await popup_info.value
                    is_new_page = True
                    try:
                        await detail_page.wait_for_url(
                            re.compile(r"/creator/detail"),
                            timeout=self.creator_detail_timeout_ms,
                        )
                    except Exception:
                        await detail_page.wait_for_selector(
                            'text="Partnered brands"',
                            timeout=self.creator_detail_timeout_ms,
                        )
                except PlaywrightTimeoutError:
                    await avatar.click()
                    detail_page = page
                    is_new_page = False
                    try:
                        await detail_page.wait_for_url(
                            re.compile(r"/creator/detail"),
                            timeout=self.creator_detail_timeout_ms,
                        )
                    except Exception:
                        await detail_page.wait_for_selector(
                            'text="Partnered brands"',
                            timeout=self.creator_detail_timeout_ms,
                        )

                if not detail_page:
                    continue

                detail_url = detail_page.url or await detail_page.evaluate("() => window.location.href")
                creator_id = self._parse_creator_id(detail_url)
                creator_name = fallback_name
                await self._close_creator_detail(detail_page, is_new_page)
                await page.wait_for_timeout(150)
                return creator_name, detail_url, creator_id
            except Exception:
                await asyncio.sleep(self.creator_detail_retry_sleep_ms / 1000)
                continue
        return None

    async def _get_avatar_element(self, row_element: Locator) -> Optional[Locator]:
        selectors = [
            '.m4b-avatar.m4b-avatar-circle.flex-shrink-0.cursor-pointer',
            '.m4b-avatar.cursor-pointer',
        ]
        for selector in selectors:
            locator = row_element.locator(selector)
            if await locator.count():
                return locator.first
        return None

    def _parse_creator_id(self, url: str) -> str:
        match = re.search(r"cid=([^&]+)", url)
        return match.group(1) if match else ""

    async def _close_creator_detail(self, detail_page: Page, is_new_page: bool) -> None:
        try:
            if is_new_page:
                await detail_page.close()
            else:
                await detail_page.keyboard.press("Escape")
        except Exception:
            pass

    async def _detect_action(
            self, row_element: Locator
    ) -> Tuple[str, List[str], List[Dict[str, Any]]]:
        recognized = {"view content", "view logistics", "approve"}
        actions: List[str] = []
        details: List[Dict[str, Any]] = []
        try:
            buttons = row_element.locator("button")
            count = await buttons.count()
            for idx in range(count):
                btn = buttons.nth(idx)
                text = ""
                try:
                    text = (await btn.inner_text()).strip()
                except Exception:
                    pass
                if not text:
                    try:
                        span_texts = await btn.locator("span").all_inner_texts()
                        text = " ".join(t.strip() for t in span_texts if t.strip())
                    except Exception:
                        text = ""
                normalized = text.lower()
                if normalized in recognized:
                    disabled = False
                    try:
                        disabled = await btn.is_disabled()
                    except Exception:
                        try:
                            disabled_attr = await btn.get_attribute("disabled")
                            aria_disabled = await btn.get_attribute("aria-disabled")
                            disabled = bool(disabled_attr) or aria_disabled == "true"
                        except Exception:
                            disabled = False
                    details.append({"label": text, "disabled": disabled})
                    actions.append(text)
        except Exception:
            return "", [], []
        return (actions[0] if actions else ""), actions, details

    async def _handle_view_content(
            self,
            page: Page,
            row_element: Locator,
            base_row: Dict[str, Any],
            expand_view_content: bool,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if not expand_view_content:
            results.append(self._empty_promotion_row(base_row))
            return results

        view_btn = row_element.locator('button:has-text("View content")').first
        if not await view_btn.count():
            return results

        # 计数器用于兼容 arco-tabs 动态 id。即使本次没打开成功，也应前进一格，避免后续错位。
        self._view_content_counter += 1

        overlay: Optional[Locator] = None
        opened_at = time.monotonic()
        try:
            for _ in range(2):
                view_btn = row_element.locator('button:has-text("View content")').first
                if not await view_btn.count():
                    break
                try:
                    await view_btn.click(timeout=3_000)
                except Exception:
                    await asyncio.sleep(0.2)
                    continue
                overlay = await self._wait_for_overlay_panel(
                    page, timeout=self.view_content_open_timeout_ms
                )
                if overlay:
                    break
            if not overlay:
                return results
            close_deadline = opened_at + (self.view_content_total_timeout_ms / 1000.0)

            detected_tab_id = await self._detect_arco_tabs_id(overlay)
            if detected_tab_id is not None:
                # 保持计数器与页面实际 arco-tabs id 对齐，避免后续探测失败时走错 id。
                self._view_content_counter = max(self._view_content_counter, detected_tab_id)

            candidate_ids: List[int] = []
            if detected_tab_id is not None:
                candidate_ids.append(int(detected_tab_id))
            candidate_ids.extend(
                [
                    int(self._view_content_counter),
                    int(self._view_content_counter - 1),
                    int(self._view_content_counter + 1),
                ]
            )
            seen_ids: Set[int] = set()
            candidate_ids = [
                cid for cid in candidate_ids
                if cid > 0 and not (cid in seen_ids or seen_ids.add(cid))
            ]

            tabs_info: List[Dict[str, Any]] = []
            for candidate in candidate_ids:
                tabs_info = await self._collect_tabs(page, candidate, overlay=overlay)
                if tabs_info:
                    break

            if not tabs_info:
                # 兜底：只抓当前已激活的 tab/panel（不等待，不强求切换成功）
                try:
                    active = overlay.locator('[role="tab"][aria-selected="true"][id^="arco-tabs-"][id*="-tab-"]').first
                    active_id = await active.get_attribute("id")
                    panel_id = await active.get_attribute("aria-controls")
                    match = re.match(r"arco-tabs-(\d+)-tab-(\d+)$", str(active_id or ""))
                    if match and panel_id:
                        tab_id = int(match.group(1))
                        tab_index = int(match.group(2))
                        tab_type = "video" if tab_index == 0 else "live"
                        tabs_info = [
                            {
                                "type": tab_type,
                                "count": None,
                                "tab_id": tab_id,
                                "tab_index": tab_index,
                                "tab_dom_id": str(active_id),
                                "panel_dom_id": str(panel_id),
                                "tab_xpath": f'//*[@id="{active_id}"]',
                                "panel_xpath": f'//*[@id="{panel_id}"]',
                            }
                        ]
                except Exception:
                    tabs_info = []
            if not tabs_info:
                return results
            drawer_rows = await self._process_view_content_tabs(
                page,
                base_row,
                tabs_info,
                overlay=overlay,
                close_deadline=close_deadline,
            )
            if drawer_rows:
                return drawer_rows
            return results
        finally:
            await self._close_view_content_drawer(page)
        return results

    async def _handle_view_logistics(
            self,
            page: Page,
            row_element: Locator,
    ) -> Optional[Dict[str, Any]]:
        view_btn = row_element.locator('button:has-text("View logistics")').first
        if not await view_btn.count():
            return None

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                await view_btn.click()
                overlay = await self._wait_for_overlay_panel(page)
                if not overlay:
                    await asyncio.sleep(1)
                    continue
                snapshot = await self._extract_logistics_snapshot(overlay)
                if snapshot:
                    return snapshot
            except Exception:
                await asyncio.sleep(1)
            finally:
                await self._close_view_content_drawer(page)
        return None

    async def _wait_for_overlay_panel(self, page: Page, timeout: int = 15_000) -> Optional[Locator]:
        deadline = time.monotonic() + timeout / 1000
        # 注意：TikTok 页面上的 drawer/modal 往往不会在 style 里显式写 `display: block`，
        # 而是依靠 class/动画；因此这里不再依赖 style 过滤，仅用 `is_visible()` 判定。
        selectors = [".arco-drawer", ".arco-modal"]
        while time.monotonic() < deadline:
            for selector in selectors:
                candidates = page.locator(selector)
                try:
                    count = await candidates.count()
                except Exception:
                    continue
                for idx in range(count - 1, -1, -1):
                    candidate = candidates.nth(idx)
                    try:
                        if not await candidate.is_visible():
                            continue
                        # 尽量确认是 View content 的抽屉，而不是其它弹窗
                        has_tabs = False
                        try:
                            has_tabs = bool(
                                await candidate.locator('[id^="arco-tabs-"][id*="-tab-"]').count()
                            )
                        except Exception:
                            has_tabs = False
                        if has_tabs:
                            return candidate
                        # fallback: 兼容文案存在但 tab 尚未渲染的短暂窗口
                        try:
                            if await candidate.get_by_text("Content details").count():
                                return candidate
                        except Exception:
                            pass
                    except Exception:
                        continue
            await asyncio.sleep(0.2)
        return None

    async def _extract_logistics_snapshot(self, overlay: Locator) -> Optional[Dict[str, Any]]:
        snapshot: Dict[str, Any] = {
            "basic_info": await self._extract_basic_info_pairs(overlay),
            "table_rows": await self._extract_table_rows(overlay),
            "timeline": await self._extract_timeline_entries(overlay),
            "raw_text": "",
        }
        try:
            snapshot["raw_text"] = (await overlay.inner_text()).strip()
        except Exception:
            snapshot["raw_text"] = ""
        if any(
                [
                    snapshot["basic_info"],
                    snapshot["table_rows"],
                    snapshot["timeline"],
                    snapshot["raw_text"],
                ]
        ):
            return snapshot
        return None

    async def _extract_basic_info_pairs(self, overlay: Locator) -> List[Dict[str, str]]:
        pairs: List[Dict[str, str]] = []
        selectors = [
            (
                ".arco-descriptions-item",
                ".arco-descriptions-item-label",
                ".arco-descriptions-item-value",
            ),
            ("div[data-logistics-field]", "xpath=.//span[1]", "xpath=.//span[last()]"),
        ]
        for item_selector, label_selector, value_selector in selectors:
            items = overlay.locator(item_selector)
            count = await items.count()
            if not count:
                continue
            for idx in range(count):
                item = items.nth(idx)
                label = await self._safe_locator_text(item.locator(label_selector))
                value = await self._safe_locator_text(item.locator(value_selector))
                if label or value:
                    pairs.append({"label": label, "value": value})
            if pairs:
                break
        return pairs

    async def _extract_table_rows(self, overlay: Locator) -> List[List[str]]:
        rows: List[List[str]] = []
        table_rows = overlay.locator("table tr")
        count = await table_rows.count()
        for idx in range(count):
            row = table_rows.nth(idx)
            cells = row.locator("th,td")
            cell_count = await cells.count()
            if cell_count == 0:
                continue
            values: List[str] = []
            for cell_index in range(cell_count):
                values.append(await self._safe_locator_text(cells.nth(cell_index)))
            if any(values):
                rows.append(values)
        return rows

    async def _extract_timeline_entries(self, overlay: Locator) -> List[Dict[str, str]]:
        timeline: List[Dict[str, str]] = []
        selectors = [
            ".arco-steps-item",
            ".arco-timeline-item",
        ]
        for selector in selectors:
            items = overlay.locator(selector)
            count = await items.count()
            if not count:
                continue
            for idx in range(count):
                item = items.nth(idx)
                title = (
                        await self._safe_locator_text(item.locator(".arco-steps-title"))
                        or await self._safe_locator_text(item.locator(".arco-timeline-item-content"))
                )
                time_text = (
                        await self._safe_locator_text(item.locator(".arco-steps-description"))
                        or await self._safe_locator_text(item.locator(".arco-timeline-item-label"))
                )
                status_text = await self._safe_locator_text(item.locator(".arco-steps-item-icon"))
                description = await self._safe_locator_text(item)
                timeline.append(
                    {
                        "title": title,
                        "time": time_text,
                        "status": status_text,
                        "description": description,
                    }
                )
            if timeline:
                break
        return timeline

    async def _safe_locator_text(self, locator: Locator) -> str:
        try:
            if await locator.count() == 0:
                return ""
            return (await locator.first.inner_text()).strip()
        except Exception:
            try:
                return (await locator.inner_text()).strip()
            except Exception:
                return ""

    def _normalize_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            norm = row.copy()
            product_id = _format_identifier(
                norm.get("platform_product_id") or norm.get("product_id")
            )
            if not product_id:
                continue
            norm["platform_product_id"] = product_id

            campaign_id = _format_identifier(
                norm.get("platform_campaign_id") or norm.get("campaign_id")
            )
            if campaign_id:
                norm["platform_campaign_id"] = campaign_id

            norm["platform_campaign_name"] = (
                    norm.get("platform_campaign_name") or norm.get("campaign_name") or ""
            )
            norm["product_name"] = norm.get("product_name") or norm.get("platform_product_name")
            norm["platform_creator_display_name"] = norm.get("creator_name") or ""
            username = (
                    norm.get("creator_username")
                    or norm.get("platform_creator_username")
                    or norm["platform_creator_display_name"].replace("@", "")
            )
            norm["platform_creator_username"] = username
            norm["creator_username"] = username
            norm["platform_creator_id"] = (
                norm.get("platform_creator_id")
                or norm.get("creator_id")
            )
            norm["product_sku"] = norm.get("product_sku") or norm.get("sku")
            norm["creator_url"] = norm.get("creator_url")
            norm["actions"] = norm.get("actions") or []
            norm["action_details"] = norm.get("action_details") or []
            norm["logistics_snapshot"] = self._normalize_logistics_snapshot(
                norm.get("logistics_snapshot")
            )

            norm["region"] = norm.get("region") or self.default_region
            norm["available_sample_count"] = _sanitize_numeric(
                norm.get("available_sample_count") or norm.get("available_samples")
            )
            norm["stock"] = _sanitize_numeric(norm.get("stock"))
            norm["post_rate"] = _sanitize_post_rate_value(norm.get("post_rate"))
            showcase_flag = _sanitize_bool(norm.get("is_showcase"))
            norm["is_showcase"] = 1 if showcase_flag else 0
            norm["request_time_remaining"] = _sanitize_request_time(
                norm.get("request_time_remaining")
            )
            uncooperative_flag = _sanitize_bool(norm.get("is_uncooperative"))
            norm["is_uncooperative"] = 1 if uncooperative_flag else 0
            unapprovable_flag = _sanitize_bool(norm.get("is_unapprovable"))
            norm["is_unapprovable"] = 1 if unapprovable_flag else 0

            norm["promotion_view_count"] = _sanitize_numeric(norm.get("promotion_view")) or 0
            norm["promotion_like_count"] = _sanitize_numeric(norm.get("promotion_like")) or 0
            norm["promotion_comment_count"] = _sanitize_numeric(norm.get("promotion_comment")) or 0
            norm["promotion_order_count"] = _sanitize_numeric(norm.get("promotion_order")) or 0
            norm["promotion_order_total_amount"] = _sanitize_decimal(norm.get("promotion_earn")) or Decimal("0")

            normalized.append(norm)
        return normalized

    def _normalize_logistics_snapshot(
            self, snapshot: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not snapshot or not isinstance(snapshot, dict):
            return None
        normalized: Dict[str, Any] = {
            "basic_info": [],
            "table_rows": [],
            "timeline": [],
            "raw_text": str(snapshot.get("raw_text", "") or "").strip(),
        }

        basic_info = snapshot.get("basic_info") or []
        for item in basic_info:
            label = str(item.get("label", "") or "").strip()
            value = str(item.get("value", "") or "").strip()
            if label or value:
                normalized["basic_info"].append({"label": label, "value": value})

        table_rows = snapshot.get("table_rows") or []
        for row in table_rows:
            if not isinstance(row, list):
                continue
            values = [str(cell or "").strip() for cell in row]
            if any(values):
                normalized["table_rows"].append(values)

        timeline = snapshot.get("timeline") or []
        for event in timeline:
            if not isinstance(event, dict):
                continue
            normalized["timeline"].append(
                {
                    "title": str(event.get("title", "") or "").strip(),
                    "time": str(event.get("time", "") or "").strip(),
                    "status": str(event.get("status", "") or "").strip(),
                    "description": str(event.get("description", "") or "").strip(),
                }
            )

        has_details = (
                normalized["basic_info"] or normalized["table_rows"] or normalized["timeline"]
        )
        if not has_details and not normalized["raw_text"]:
            return None
        return normalized


    async def _collect_tabs(
        self,
        page: Page,
        tab_id: int,
        *,
        overlay: Optional[Locator] = None,
    ) -> List[Dict[str, Any]]:
        """收集 View content 抽屉里的 video/live tab 信息。

        注意：页面上可能残留历史 drawer DOM（隐藏态），因此优先在 overlay 范围内查找。
        """
        tabs: List[Dict[str, Any]] = []
        root: Union[Page, Locator] = overlay or page
        prefix = ".//" if overlay is not None else "//"

        for tab_index in range(2):
            tab_dom_id = f"arco-tabs-{tab_id}-tab-{tab_index}"
            panel_dom_id = f"arco-tabs-{tab_id}-panel-{tab_index}"
            tab_xpath = f'{prefix}*[@id="{tab_dom_id}"]'
            panel_xpath = f'{prefix}*[@id="{panel_dom_id}"]'

            tab_locator = root.locator(f"xpath={tab_xpath}")
            try:
                if not await tab_locator.count():
                    continue
            except Exception:
                continue

            text_locator = tab_locator.locator("xpath=./span/span").first
            try:
                full_text = (await text_locator.inner_text()).strip()
            except Exception:
                continue

            lowered = full_text.lower()
            tab_type: Optional[str] = None
            if "video" in lowered or "videos" in lowered or "视频" in lowered:
                tab_type = "video"
            elif "live" in lowered or "直播" in lowered:
                tab_type = "live"
            if not tab_type:
                tab_type = "video" if tab_index == 0 else "live"

            count_match = re.search(r"(\d+)", full_text)
            tab_count = int(count_match.group(1)) if count_match else None
            tabs.append(
                {
                    "type": tab_type,
                    "count": tab_count,
                    "tab_id": tab_id,
                    "tab_index": tab_index,
                    "tab_dom_id": tab_dom_id,
                    "panel_dom_id": panel_dom_id,
                    # 提取 promotion 数据时仍使用绝对 xpath（其余函数拼接依赖它）
                    "tab_xpath": f'//*[@id="{tab_dom_id}"]',
                    "panel_xpath": f'//*[@id="{panel_dom_id}"]',
                }
            )

        return tabs

    async def _detect_arco_tabs_id(self, overlay: Locator) -> Optional[int]:
        """从 overlay 内部探测当前 arco-tabs 组件的动态 id。"""
        # 优先从“当前激活 tab”反推出 tab_id，避免页面上残留的隐藏 drawer DOM 干扰计数结果。
        try:
            active_id = await overlay.locator(
                '[role="tab"][aria-selected="true"][id^="arco-tabs-"][id*="-tab-"]'
            ).first.get_attribute("id")
        except Exception:
            active_id = None
        if active_id:
            match = re.match(r"arco-tabs-(\d+)-tab-\d+$", str(active_id))
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        try:
            ids = await overlay.locator('[id^="arco-tabs-"][id*="-tab-"]').evaluate_all(
                "els => els.map(e => e.id)"
            )
        except Exception:
            return None
        if not isinstance(ids, list):
            return None
        counts: Dict[int, int] = {}
        for element_id in ids:
            if not isinstance(element_id, str):
                continue
            match = re.match(r"arco-tabs-(\d+)-tab-\d+$", element_id)
            if not match:
                continue
            try:
                number = int(match.group(1))
            except ValueError:
                continue
            counts[number] = counts.get(number, 0) + 1
        if not counts:
            return None
        # 同一 overlay 内可能存在多个 tabs 组件；优先选择出现次数最多的，次数相同则取 tab_id 更大的。
        return max(counts.items(), key=lambda item: (item[1], item[0]))[0]

    async def _wait_for_content_tabs(
        self,
        page: Page,
        tab_id: int,
        *,
        overlay: Optional[Locator] = None,
        attempts: int = 20,
        wait_ms: int = 250,
    ) -> List[Dict[str, Any]]:
        effective_tab_id = tab_id
        best: List[Dict[str, Any]] = []
        best_types: Set[str] = set()
        first_seen_at: Optional[int] = None
        # tab-1 往往会稍晚渲染；在首次看到 tab 后额外等待一小段时间，避免漏掉第二个 tab。
        grace_attempts = max(1, int(self.view_content_tabs_grace_ms / max(wait_ms, 1)))
        effective_attempts = max(attempts, grace_attempts + 2)
        root: Union[Page, Locator] = overlay or page
        prefix = ".//" if overlay is not None else "//"
        for attempt_index in range(effective_attempts):
            if overlay is not None:
                detected = await self._detect_arco_tabs_id(overlay)
                if detected is not None:
                    effective_tab_id = detected
            tabs = await self._collect_tabs(page, effective_tab_id, overlay=overlay)
            if tabs:
                current_types = {str(item.get("type")) for item in tabs if item.get("type")}
                if len(current_types) > len(best_types):
                    best = tabs
                    best_types = current_types
                # 若同时识别到 video/live，则认为 tab 已完整渲染
                if "video" in current_types and "live" in current_types:
                    return tabs
                if first_seen_at is None:
                    first_seen_at = attempt_index
                elif attempt_index - first_seen_at >= grace_attempts:
                    return best
            else:
                # 有些场景下 tab dom id 已经出现但文本未渲染，避免完全依赖 tabs 列表出现才开始 grace 计时。
                if first_seen_at is None:
                    try:
                        exists = bool(
                            await root.locator(
                                f'xpath={prefix}*[@id="arco-tabs-{effective_tab_id}-tab-0"]'
                            ).count()
                        )
                    except Exception:
                        exists = False
                    if exists:
                        first_seen_at = attempt_index
            await page.wait_for_timeout(wait_ms)
        return best

    async def _process_view_content_tabs(
            self,
            page: Page,
            base_row: Dict[str, Any],
            tabs_info: List[Dict[str, Any]],
            *,
            overlay: Optional[Locator] = None,
            close_deadline: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        drawer_rows: List[Dict[str, Any]] = []
        # 保持固定顺序：video -> live（即使 UI tab 顺序不同）
        type_order = {"video": 0, "live": 1}
        ordered_tabs = sorted(
            tabs_info,
            key=lambda item: (
                type_order.get(str(item.get("type") or "").lower(), 9),
                int(item.get("tab_index") or 0),
            ),
        )
        root: Union[Page, Locator] = overlay or page
        prefix = ".//" if overlay is not None else "//"

        for tab_info in ordered_tabs:
            if close_deadline is not None:
                remaining_total_s = close_deadline - time.monotonic()
                if remaining_total_s <= 0:
                    break
            else:
                remaining_total_s = None

            tab_budget_s = self.view_content_tab_timeout_ms / 1000.0
            if remaining_total_s is not None:
                tab_budget_s = min(tab_budget_s, max(0.1, remaining_total_s))

            async def _run_one_tab() -> None:
                tab_dom_id = str(tab_info.get("tab_dom_id") or "")
                panel_dom_id = str(tab_info.get("panel_dom_id") or "")
                if not tab_dom_id:
                    tab_dom_id = f"arco-tabs-{tab_info.get('tab_id')}-tab-{tab_info.get('tab_index')}"
                if not panel_dom_id:
                    panel_dom_id = f"arco-tabs-{tab_info.get('tab_id')}-panel-{tab_info.get('tab_index')}"

                tab_xpath = tab_info.get("tab_xpath") or f'//*[@id="{tab_dom_id}"]'
                panel_xpath = tab_info.get("panel_xpath") or f'//*[@id="{panel_dom_id}"]'

                try:
                    tab_locator = root.locator(f'xpath={prefix}*[@id="{tab_dom_id}"]').first
                    await tab_locator.scroll_into_view_if_needed()
                    await tab_locator.click(timeout=5_000)
                except Exception:
                    try:
                        await page.locator(f'xpath=//*[@id="{tab_dom_id}"]').first.click(timeout=5_000, force=True)
                    except Exception:
                        pass

                try:
                    await root.locator(f'xpath={prefix}*[@id="{panel_dom_id}"]').first.wait_for(
                        timeout=3_000
                    )
                except Exception:
                    pass
                await asyncio.sleep(self.view_content_tab_settle_ms / 1000)

                promotions = await self._extract_promotion_data_by_xpath(
                    page,
                    str(panel_xpath),
                    str(tab_info.get("type") or ""),
                    expected_total=tab_info.get("count"),
                )
                for promo in promotions:
                    row = self._empty_promotion_row(base_row)
                    row["type"] = str(tab_info.get("type") or "")
                    tab_count = tab_info.get("count")
                    row["type_number"] = str(tab_count) if isinstance(tab_count, int) else ""
                    row.update(promo)
                    drawer_rows.append(row)

            try:
                await asyncio.wait_for(_run_one_tab(), timeout=tab_budget_s)
            except asyncio.TimeoutError:
                logger.warning("View content 单 tab 处理超时，跳过该 tab", tab_type=tab_info.get("type"))
                continue
            except Exception:
                continue
        return drawer_rows

    async def _extract_promotion_data_by_xpath(
            self,
            page: Page,
            panel_xpath: str,
            content_type: str,
            *,
            expected_total: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        panel_locator = page.locator(f"xpath={panel_xpath}")
        try:
            await panel_locator.wait_for(timeout=5_000)
        except Exception:
            return []

        expected_total_int: Optional[int] = None
        try:
            if isinstance(expected_total, int) and expected_total > 0:
                expected_total_int = expected_total
        except Exception:
            expected_total_int = None

        max_pages = 20
        if expected_total_int:
            # 经验值：View content 抽屉通常按 10 条分页，避免过度翻页
            max_pages = min(max_pages, max(1, (expected_total_int + 9) // 10))

        for _ in range(max_pages):
            promotion_list = await self._extract_promotion_data_single_page_by_xpath(
                page,
                panel_xpath,
                content_type,
            )
            if not promotion_list:
                break
            for promo in promotion_list:
                if not promo or not any(promo.values()):
                    continue
                signature = json.dumps(promo, sort_keys=True, ensure_ascii=False, default=str)
                if signature in seen:
                    continue
                seen.add(signature)
                collected.append(promo)

            if expected_total_int is not None and len(collected) >= expected_total_int:
                break

            next_btn = panel_locator.locator("li.arco-pagination-item-next").first
            if not await next_btn.count():
                break
            if await self._is_pagination_next_disabled(next_btn):
                break

            marker = await self._read_promotion_page_marker(page, panel_xpath, content_type)
            try:
                await next_btn.scroll_into_view_if_needed()
                await next_btn.click(timeout=3_000)
            except Exception:
                break

            changed = await self._wait_for_promotion_page_changed(
                page,
                panel_xpath,
                content_type,
                previous_marker=marker,
                timeout_ms=3_000,
            )
            if not changed and marker:
                # 点击翻页后内容没有变化，避免无意义重复等待
                break

        return collected

    async def _extract_promotion_data_single_page_by_xpath(
        self,
        page: Page,
        panel_xpath: str,
        content_type: str,
    ) -> List[Dict[str, Any]]:
        # Special single-layout detection
        special_xpath = f"{panel_xpath}/div/div/div/div[2]/div/span/div"
        special_locator = page.locator(f"xpath={special_xpath}")
        if await special_locator.count():
            special_promotions = await self._extract_special_layout_promotions(
                page,
                panel_xpath,
                content_type,
            )
            if special_promotions:
                return special_promotions

        block_base_xpath = (
            f"{panel_xpath}/div/div" if content_type == "video" else f"{panel_xpath}/div"
        )
        blocks_locator = page.locator(f"xpath={block_base_xpath}/div")
        blocks_count = await blocks_locator.count()
        if blocks_count == 0:
            try:
                await blocks_locator.first.wait_for(timeout=2500)
            except Exception:
                return []
            blocks_count = await blocks_locator.count()

        promotion_list: List[Dict[str, Any]] = []
        for idx in range(1, blocks_count + 1):
            block_xpath = f"{block_base_xpath}/div[{idx}]"
            promo = await self._extract_single_block_with_retry(
                page,
                block_xpath,
                content_type,
                idx,
            )
            if promo and any(promo.values()):
                promotion_list.append(promo)
        return promotion_list

    async def _is_pagination_next_disabled(self, next_btn: Locator) -> bool:
        try:
            disabled_attr = await next_btn.get_attribute("aria-disabled")
            if disabled_attr == "true":
                return True
        except Exception:
            pass
        try:
            class_attr = (await next_btn.get_attribute("class")) or ""
            return "arco-pagination-item-disabled" in class_attr
        except Exception:
            return False

    async def _read_promotion_page_marker(
        self,
        page: Page,
        panel_xpath: str,
        content_type: str,
    ) -> str:
        block_base_xpath = (
            f"{panel_xpath}/div/div" if content_type == "video" else f"{panel_xpath}/div"
        )
        first_block_xpath = f"{block_base_xpath}/div[1]"
        if content_type == "video":
            base = f"{first_block_xpath}/div[2]/div"
        else:
            base = f"{first_block_xpath}/div/div"
        name = await self._safe_text_by_xpath(page, f"{base}/div[1]")
        time_text = await self._safe_text_by_xpath(page, f"{base}/div[2]")
        marker = f"{name}|{time_text}".strip("|")
        return marker

    async def _wait_for_promotion_page_changed(
        self,
        page: Page,
        panel_xpath: str,
        content_type: str,
        *,
        previous_marker: str,
        timeout_ms: int,
    ) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            marker = await self._read_promotion_page_marker(page, panel_xpath, content_type)
            if marker and marker != previous_marker:
                return True
            await asyncio.sleep(0.15)
        return False

    async def _extract_special_layout_promotions(
            self,
            page: Page,
            panel_xpath: str,
            content_type: str,
    ) -> List[Dict[str, Any]]:
        base_path = f"{panel_xpath}/div/div/div/div[2]/div"
        max_retries = 3
        for attempt in range(max_retries):
            try:
                promo: Dict[str, Any] = {}
                promo["promotion_name"] = await self._safe_text_by_xpath(page, f"{base_path}/span/div")
                promo["promotion_time"] = await self._safe_text_by_xpath(page, f"{base_path}/div[1]")
                metrics_base = f"{base_path}/div[2]"
                promo["promotion_view"] = await self._extract_metric_value(page, metrics_base, 1)
                promo["promotion_like"] = await self._extract_metric_value(page, metrics_base, 2)
                promo["promotion_comment"] = await self._extract_metric_value(page, metrics_base, 3)
                promo["promotion_order"] = await self._extract_metric_value(page, metrics_base, 4)
                promo["promotion_earn"] = _clean_promotion_earn_text(
                    await self._extract_metric_value(page, metrics_base, 5)
                )
                if promo and any(promo.values()):
                    return [promo]
            except Exception:
                await asyncio.sleep(1)
                continue
        return []

    async def _extract_single_block_with_retry(
            self,
            page: Page,
            block_xpath: str,
            content_type: str,
            block_index: int,
            max_retries: int = 2,
    ) -> Dict[str, Any]:
        for attempt in range(max_retries):
            try:
                promo = await self._extract_single_block_by_xpath(
                    page,
                    block_xpath,
                    content_type,
                )
                if any(promo.values()):
                    return promo
            except Exception:
                await asyncio.sleep(0.2)
        return {}

    async def _extract_single_block_by_xpath(
            self,
            page: Page,
            block_xpath: str,
            content_type: str,
    ) -> Dict[str, Any]:
        if content_type == "video":
            block_base = f"{block_xpath}/div[2]/div"
            name_xpath = f"{block_base}/div[1]"
            time_xpath = f"{block_base}/div[2]"
            metrics_base = f"{block_base}/div[3]"
        else:
            block_base = f"{block_xpath}/div/div"
            name_xpath = f"{block_base}/div[1]"
            time_xpath = f"{block_base}/div[2]"
            metrics_base = f"{block_base}/div[3]"

        promotion_name = await self._safe_text_by_xpath(page, name_xpath)
        promotion_time = await self._safe_text_by_xpath(page, time_xpath)

        promotion_view = await self._extract_metric_value(page, metrics_base, 1)
        promotion_like = await self._extract_metric_value(page, metrics_base, 2)
        promotion_comment = await self._extract_metric_value(page, metrics_base, 3)
        promotion_order = await self._extract_metric_value(page, metrics_base, 4)
        promotion_earn = await self._extract_metric_value(page, metrics_base, 5)

        return {
            "promotion_name": promotion_name,
            "promotion_time": promotion_time,
            "promotion_view": promotion_view,
            "promotion_like": promotion_like,
            "promotion_comment": promotion_comment,
            "promotion_order": promotion_order,
            "promotion_earn": _clean_promotion_earn_text(promotion_earn),
        }

    def _empty_promo_metrics(self) -> Dict[str, Any]:
        return {
            "promotion_name": "",
            "promotion_time": "",
            "promotion_view": "",
            "promotion_like": "",
            "promotion_comment": "",
            "promotion_order": "",
            "promotion_earn": "",
        }

    async def _close_view_content_drawer(self, page: Page) -> None:
        closed_any = False
        try:
            for _ in range(3):
                found_overlay = False
                drawers = page.locator(".arco-drawer")
                drawer_count = await drawers.count()
                for idx in range(drawer_count):
                    drawer = drawers.nth(idx)
                    try:
                        if not await drawer.is_visible():
                            continue
                    except Exception:
                        continue
                    close_btn = drawer.locator(
                        "span.arco-icon-hover.arco-drawer-close-icon"
                    ).first
                    if await close_btn.count():
                        await close_btn.click()
                        closed_any = True
                        found_overlay = True
                        break
                if found_overlay:
                    await page.wait_for_timeout(300)
                    continue

                modals = page.locator(".arco-modal")
                modal_count = await modals.count()
                for idx in range(modal_count):
                    modal = modals.nth(idx)
                    try:
                        if not await modal.is_visible():
                            continue
                    except Exception:
                        continue
                    close_btn = modal.locator('[aria-label="Close"]').first
                    if not await close_btn.count():
                        close_btn = modal.locator('button:has-text("Close")').first
                    if await close_btn.count():
                        await close_btn.click()
                        closed_any = True
                        found_overlay = True
                        break
                if found_overlay:
                    await page.wait_for_timeout(300)
                    continue
                break
        except Exception:
            pass

        if not closed_any:
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

    async def _has_visible_overlay(self, page: Page) -> bool:
        selectors = [
            ".arco-drawer[style*='display: block']",
            ".arco-modal[style*='display: block']",
            "div[data-tid='m4b_drawer']",
        ]
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = await locator.count()
            except Exception:
                continue
            for idx in range(count):
                element = locator.nth(idx)
                try:
                    if await element.is_visible():
                        return True
                except Exception:
                    continue
        return False

    async def _dismiss_active_overlays(self, page: Page, max_attempts: int = 3) -> None:
        for _ in range(max_attempts):
            if not await self._has_visible_overlay(page):
                return
            await self._close_view_content_drawer(page)
            await page.wait_for_timeout(200)

    async def _persist_results(self, rows: List[Dict[str, Any]], options: CrawlOptions) -> None:
        if not rows:
            raise MessageProcessingError("No valid rows to persist")

        operator_id = self.operator_id or getattr(
            settings,
            "SAMPLE_DEFAULT_OPERATOR_ID",
            "00000000-0000-0000-0000-000000000000",
        )
        options_payload = asdict(options)
        try:
            await self.ingestion_client.submit(
                source=self.service_name,
                operator_id=operator_id,
                options=options_payload,
                rows=rows,
            )
        except NonRetryableMessageError:
            raise
        except MessageProcessingError:
            raise
        except Exception as exc:
            raise MessageProcessingError(f"Failed to submit rows to inner API: {exc}") from exc

    def _export_rows(self, rows: List[Dict[str, Any]], options: CrawlOptions, page_index: Optional[int] = None) -> None:
        if not rows:
            return
        self.export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        campaign_fragment = _format_identifier(options.campaign_id) or "all"
        safe_campaign = re.sub(r"[^0-9A-Za-z]+", "_", campaign_fragment)
        tab_fragment = "-".join(options.tabs) if options.tabs else "all"
        safe_tab = re.sub(r"[^0-9A-Za-z-]+", "_", tab_fragment) or "all"
        page_suffix = f"_page{page_index}" if page_index is not None else ""
        file_stem = f"samples_{options.region.lower()}_{safe_campaign}_{safe_tab}_{timestamp}{page_suffix}"

        df = pd.DataFrame(rows)
        json_columns = ["actions", "action_details", "logistics_snapshot"]
        for column in json_columns:
            if column in df.columns:
                df[column] = df[column].apply(
                    lambda value: json.dumps(value, ensure_ascii=False, default=str)
                    if isinstance(value, (list, dict))
                    else value
                )

        column_order = [
            "region",
            "product_name",
            "platform_product_id",
            "stock",
            "product_sku",
            "available_sample_count",
            "status",
            "request_time_remaining",
            "platform_campaign_name",
            "platform_campaign_id",
            "action",
            "actions",
            "action_details",
            "platform_creator_display_name",
            "platform_creator_username",
            "creator_name",
            "creator_url",
            "creator_id",
            "creator_tiktok",
            "post_rate",
            "is_showcase",
            "type",
            "type_number",
            "promotion_name",
            "promotion_time",
            "promotion_view_count",
            "promotion_like_count",
            "promotion_comment_count",
            "promotion_order_count",
            "promotion_order_total_amount",
            "extracted_time",
            "logistics_snapshot",
        ]

        existing_columns = [column for column in column_order if column in df.columns]
        remaining_columns = [column for column in df.columns if column not in existing_columns]
        export_df = df[existing_columns + remaining_columns]

        xlsx_path = self.export_dir / f"{file_stem}.xlsx"
        csv_path = self.export_dir / f"{file_stem}.csv"
        export_df.to_excel(xlsx_path, index=False)
        export_df.to_csv(csv_path, index=False)
        logger.info("导出 %s 行样品数据到 %s 和 %s", len(export_df), xlsx_path, csv_path)

    async def _click_tab(self, page: Page, tab_name: str) -> None:
        target_text = self.tab_mapping.get(tab_name.lower(), tab_name)
        locator = page.locator("div.arco-tabs-header-title-text")
        count = await locator.count()
        for idx in range(count):
            item = locator.nth(idx)
            text = (await item.inner_text()).strip()
            normalized = text.lower().replace("\n", "")
            if tab_name.lower() in normalized or target_text.lower() in normalized:
                self._active_tab_name = target_text
                self._active_tab_slug = self._tab_slug_for(target_text)
                try:
                    async with page.expect_response(
                        lambda resp: self._is_partner_sample_records_url(resp.url),
                        timeout=20_000,
                    ) as resp_info:
                        await item.click()
                    response = await resp_info.value
                    await self._update_sample_records_context(response)
                except PlaywrightTimeoutError:
                    await item.click()
                await asyncio.sleep(0.5)
                return

    async def _capture_tab_snapshot(self, page: Page) -> None:
        self._tab_snapshot = await self._read_tab_counters(page)

    async def _detect_tab_updates(self) -> Dict[str, Dict[str, int]]:
        if not self._main_page or self._main_page.is_closed():
            return {}
        current = await self._read_tab_counters(self._main_page)
        diff: Dict[str, Dict[str, int]] = {}
        for key, value in current.items():
            prev = self._tab_snapshot.get(key)
            if prev is None or prev != value:
                diff[key] = {"previous": prev or 0, "current": value}
        self._tab_snapshot = current
        return diff

    async def _read_tab_counters(self, page: Page) -> Dict[str, int]:
        results: Dict[str, int] = {}
        locator = page.locator("div.arco-tabs-header-title")
        count = await locator.count()
        for idx in range(count):
            try:
                element = locator.nth(idx)
                text = (await element.inner_text()).strip().replace("\n", "")
                match = re.match(r"([A-Za-z ]+)(\d+)", text)
                if match:
                    label = match.group(1).strip().lower()
                    value = int(match.group(2))
                    results[label] = value
            except Exception:
                continue
        return results

    async def _is_logged_in(self, page: Page) -> bool:
        return await self.login_manager.is_logged_in(page)

    async def _safe_text_by_xpath(
            self,
            page: Page,
            xpath: str,
            timeout: int = 2000,
    ) -> str:
        try:
            locator = page.locator(f"xpath={xpath}")
            if await locator.count() == 0:
                return ""
            # 不做显式 wait：DOM 结构经常变化/切 tab 后节点被隐藏，等待会造成“看似已加载但卡住”。
            return (await locator.first.inner_text()).strip()
        except Exception:
            return ""

    async def _extract_metric_value(self, page: Page, metrics_base: str, metric_index: int) -> str:
        """从 View content 的 metrics 区块提取数值，兼容 video/live 两套 DOM 结构。"""
        candidates = [
            f"{metrics_base}/div[{metric_index}]/div[2]/div",
            f"{metrics_base}/div[{metric_index}]/div[2]/span/div",
            f"{metrics_base}/div[{metric_index}]/div[2]/div/span",
            f"{metrics_base}/div[{metric_index}]/div[2]/div/div",
            # 有些 live 布局数值直接在 div[2] 上（无子 div/span）
            f"{metrics_base}/div[{metric_index}]/div[2]",
        ]
        for xpath in candidates:
            text = await self._safe_text_by_xpath(page, xpath)
            if text:
                return text
        return ""

    async def _has_next_page(self, page: Page) -> bool:
        try:
            next_btn = page.locator("li.arco-pagination-item-next").first
            await next_btn.wait_for(state="attached", timeout=3_000)
            disabled_attr = await next_btn.get_attribute("aria-disabled")
            class_attr = (await next_btn.get_attribute("class")) or ""
            disabled = (disabled_attr == "true") or ("arco-pagination-item-disabled" in class_attr)
            logger.debug("分页检测: next_btn disabled=%s class=%s attr=%s", disabled, class_attr, disabled_attr)
            return not disabled
        except Exception as exc:
            logger.debug("分页检测失败，视为无下一页: %s", exc)
            return False

    async def _goto_next_page(self, page: Page) -> bool:
        for attempt in range(3):
            try:
                await self._dismiss_active_overlays(page)
                next_btn = page.locator("li.arco-pagination-item-next").first
                await next_btn.scroll_into_view_if_needed()
                try:
                    async with page.expect_response(
                        lambda resp: self._is_partner_sample_records_url(resp.url),
                        timeout=20_000,
                    ) as resp_info:
                        await next_btn.click()
                    response = await resp_info.value
                    await self._update_sample_records_context(response)
                except PlaywrightTimeoutError as exc:
                    logger.debug("捕获下一页 sample records 请求超时: %s", exc)
                    await asyncio.sleep(1)
                    continue
                await page.wait_for_timeout(3000)
                # 等待新一页数据渲染
                try:
                    await page.wait_for_selector("tbody tr", timeout=15_000)
                except Exception:
                    pass
                return True
            except Exception as exc:
                logger.debug("点击下一页失败（第 %s 次）: %s", attempt + 1, exc)
                await asyncio.sleep(1)
        return False

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
            logger.warning("Failed to load accounts config (%s): %s", path, exc)
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
            login_email=getattr(settings, "SAMPLE_LOGIN_EMAIL", ""),
            login_password=getattr(settings, "SAMPLE_LOGIN_PASSWORD", ""),
            gmail_username=getattr(settings, "SAMPLE_GMAIL_USERNAME", ""),
            gmail_app_password=getattr(settings, "SAMPLE_GMAIL_APP_PASSWORD", ""),
            region=desired_region,
            creator_id=getattr(settings, "SAMPLE_DEFAULT_OPERATOR_ID", None),
        )

    def _expand_tab_keys(self, entries: List[str]) -> List[str]:
        resolved: List[str] = []
        seen: Set[str] = set()
        for entry in entries:
            normalized = str(entry or "").strip().lower()
            if not normalized:
                continue
            canonical = self.tab_key_lookup.get(normalized, normalized)
            if canonical == "all":
                for key in self.iterable_tab_keys:
                    if key not in seen:
                        resolved.append(key)
                        seen.add(key)
                continue
            if canonical not in seen:
                resolved.append(canonical)
                seen.add(canonical)
        return resolved

    def _build_options(self, payload: Dict[str, Any]) -> CrawlOptions:
        def _pick(*keys: str, default: Any = None) -> Any:
            for key in keys:
                if key in payload:
                    value = payload.get(key)
                    if value is not None:
                        return value
            return default

        region = str(_pick("region", default=self.default_region or "MX")).upper()
        account_name = _pick("account_name", "accountName")
        expand_view_content = bool(
            _pick(
                "expand_view_content",
                "expandViewContent",
                default=self.expand_view_content_default,
            )
        )
        manual_login = bool(
            _pick("manual_login", "manualLogin", default=self.manual_login_default)
        )
        max_pages = _pick("max_pages", "maxPages")
        max_pages_int = None
        if isinstance(max_pages, int):
            max_pages_int = max_pages if max_pages > 0 else None
        elif isinstance(max_pages, str) and max_pages.isdigit():
            max_pages_int = int(max_pages)

        raw_tab = str(
            _pick("tab", "tab_name", "tabName", default=self.default_tab or "all")
        ).lower()
        tabs_payload = _pick("tabs")
        if isinstance(tabs_payload, list) and tabs_payload:
            tab_keys = self._expand_tab_keys([str(tab).lower() for tab in tabs_payload])
        else:
            tab_keys = self._expand_tab_keys([raw_tab]) or [raw_tab]

        campaign_ids_payload = _pick(
            "campaign_ids",
            "campaignIds",
            "campaign_id_list",
            "campaignIdList",
            "campaign_id_list",
        )
        campaign_ids: List[str] = []
        if isinstance(campaign_ids_payload, list):
            campaign_ids = [str(cid).strip() for cid in campaign_ids_payload if str(cid).strip()]
        elif isinstance(campaign_ids_payload, str):
            # 兼容脚本误传字符串：支持单个 id 或逗号分隔的多个 id
            text = campaign_ids_payload.strip()
            if text:
                parts = [part.strip() for part in re.split(r"[,\n\r\t ]+", text) if part.strip()]
                campaign_ids = parts

        campaign_id = _pick("campaign_id", "campaignId")
        if campaign_id:
            campaign_id = str(campaign_id).strip()
            if campaign_id and not campaign_ids:
                campaign_ids = [campaign_id]

        scan_all_pages = bool(
            _pick(
                "scan_all_pages",
                "scanAllPages",
                default=not bool(campaign_id or campaign_ids),
            )
        )

        normalized_tabs = [self.tab_mapping.get(tab, tab) for tab in tab_keys]
        if not normalized_tabs:
            normalized_tabs = [self.tab_mapping.get("review", "To review")]

        export_excel = bool(
            _pick("export_excel", "exportExcel", default=self.export_excel_enabled)
        )
        view_logistics = bool(
            _pick("view_logistics", "viewLogistics", default=self.view_logistics_default)
        )

        return CrawlOptions(
            campaign_id=campaign_id,
            campaign_ids=campaign_ids,
            account_name=account_name,
            region=region,
            tabs=normalized_tabs,
            expand_view_content=expand_view_content,
            max_pages=max_pages_int,
            scan_all_pages=scan_all_pages,
            export_excel=export_excel,
            view_logistics=view_logistics,
            manual_login=manual_login,
        )
