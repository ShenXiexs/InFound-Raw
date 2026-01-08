from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from common.core.config import get_settings
from common.core.database import get_db
from common.core.exceptions import PlaywrightError
from common.core.logger import get_logger
from common.models.all import CreatorCrawlLogs
from sqlalchemy import func, or_, select
from apps.portal_tiktok_sample_crawler.services.email_verifier import GmailVerificationCode
from .creator_ingestion_client import CreatorIngestionClient
from .outreach_task_client import OutreachTaskClient
from .outreach_chatbot_client import OutreachChatbotClient
from .outreach_chatbot_control_client import OutreachChatbotControlClient

CATEGORY_NAME_TO_ID = {
    "Home Supplies": "600001",
    "Kitchenware": "600024",
    "Textiles & Soft Furnishings": "600154",
    "Household Appliances": "600942",
    "Womenswear & Underwear": "601152",
    "Shoes": "601352",
    "Beauty & Personal Care": "601450",
    "Beauty": "601450",
    "Skincare": "601450",
    "Skin Care": "601450",
    "Phones & Electronics": "601739",
    "Computers & Office Equipment": "601755",
    "Pet Supplies": "602118",
    "Sports & Outdoor": "603014",
    "Toys": "604206",
    "Furniture": "604453",
    "Tools & Hardware": "604579",
    "Home Improvement": "604968",
    "Automotive & Motorcycle": "605196",
    "Fashion Accessories": "605248",
    "Food & Beverages": "700437",
    "Health": "700645",
    "Books, Magazines & Audio": "801928",
    "Kids' Fashion": "802184",
    "Menswear & Underwear": "824328",
    "Luggage & Bags": "824584",
    "Collections": "951432",
    "Jewellery Accessories & Derivatives": "953224",
}
CATEGORY_ID_TO_NAME = {value: key for key, value in CATEGORY_NAME_TO_ID.items()}
CATEGORY_NAME_TO_ID_LOWER = {key.lower(): value for key, value in CATEGORY_NAME_TO_ID.items()}


@dataclass
class AccountProfile:
    name: str
    account_id: str
    login_email: str
    login_password: Optional[str]
    gmail_username: str
    gmail_app_password: str
    region: str
    enabled: bool = True


class CreatorCrawlerService:
    """Creator crawler that mirrors login + filter + search behavior."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self.headless = bool(getattr(self.settings, "PLAYWRIGHT_HEADLESS", True))

        self.target_url = getattr(
            self.settings,
            "CREATOR_TARGET_URL",
            "https://partner.tiktokshop.com/affiliate-cmp/creator?market=19",
        )
        self.login_url = getattr(
            self.settings,
            "CREATOR_LOGIN_URL",
            "https://partner-sso.tiktok.com/account/login?from=ttspc_logout&redirectURL=%2F%2Fpartner.tiktokshop.com%2Fhome&lang=en",
        )
        self.account_config_path = getattr(
            self.settings, "CREATOR_ACCOUNT_CONFIG_PATH", "configs/accounts.json"
        )
        self.default_region = str(
            getattr(self.settings, "CREATOR_DEFAULT_REGION", "MX") or "MX"
        ).upper()
        self.max_creators_to_load = int(
            getattr(self.settings, "CREATOR_MAX_CREATORS_TO_LOAD", 400) or 400
        )
        self.max_scroll_attempts = int(
            getattr(self.settings, "CREATOR_MAX_SCROLL_ATTEMPTS", 50) or 50
        )
        self.manual_email_code_input = bool(
            getattr(self.settings, "MANUAL_EMAIL_CODE_INPUT", False)
        )
        self.manual_email_code_input_timeout_seconds = int(
            getattr(self.settings, "MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS", 180) or 180
        )

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._initialize_lock = asyncio.Lock()
        self._run_lock = asyncio.Lock()
        self._prewarm_lock = asyncio.Lock()
        self._prewarmed = False

        self.accounts_data = self._load_accounts_config()
        self.account_profile: Optional[AccountProfile] = None
        self.gmail_verifier: Optional[GmailVerificationCode] = None
        self.region = self.default_region

        self.default_search_strategy = self._build_default_search_strategy()
        self.search_strategy: Dict[str, Any] = dict(self.default_search_strategy)
        self.search_keywords_raw = ""
        self.search_keyword = ""
        self.brand_name = ""
        self.task_metadata: Dict[str, Any] = {}
        self.task_id: Optional[str] = None
        self.source = "portal_tiktok_creator_crawler"
        self.db_actor_id: Optional[str] = None
        self.task_started_at: Optional[datetime] = None
        self.task_finished_at: Optional[datetime] = None
        self.plan_execute_time: Optional[datetime] = None
        self.plan_stop_time: Optional[datetime] = None
        self.run_deadline: Optional[datetime] = None
        self.stop_reason: Optional[str] = None
        self.only_first = 0
        self.first_message_text = ""
        self.later_message_text = ""

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
        self.outreach_task_client = OutreachTaskClient(
            base_url=self.settings.INNER_API_BASE_URL,
            task_path=self.settings.INNER_API_OUTREACH_TASK_PATH,
            progress_path=self.settings.INNER_API_OUTREACH_PROGRESS_PATH,
            header_name=self.settings.INNER_API_AUTH_REQUIRED_HEADER,
            token=inner_api_token,
            timeout=float(self.settings.INNER_API_TIMEOUT),
        )
        self.outreach_chatbot_client = OutreachChatbotClient(
            base_url=self.settings.INNER_API_BASE_URL,
            chatbot_path=self.settings.INNER_API_OUTREACH_CHATBOT_PATH,
            header_name=self.settings.INNER_API_AUTH_REQUIRED_HEADER,
            token=inner_api_token,
            timeout=float(self.settings.INNER_API_TIMEOUT),
        )
        self.outreach_control_client = OutreachChatbotControlClient(
            base_url=self.settings.INNER_API_BASE_URL,
            control_path=self.settings.INNER_API_OUTREACH_CONTROL_PATH,
            header_name=self.settings.INNER_API_AUTH_REQUIRED_HEADER,
            token=inner_api_token,
            timeout=float(self.settings.INNER_API_TIMEOUT),
        )
        self._outreach_control_started = False

    def _normalized_region(self) -> str:
        return (self.region or "").strip().upper()

    def _partner_domain(self) -> str:
        region = self._normalized_region()
        if region in {"FR", "ES"}:
            return "partner.eu.tiktokshop.com"
        return "partner.tiktokshop.com"

    def _market_id(self) -> str:
        market_mapping = {
            "MX": "19",
            "FR": "17",
            "ES": "14",
        }
        return market_mapping.get(self._normalized_region(), "19")

    def _build_creator_url(self) -> str:
        return f"https://{self._partner_domain()}/affiliate-cmp/creator?market={self._market_id()}"

    def _build_chat_url(self, creator_id: str) -> str:
        creator_id = str(creator_id or "").strip()
        if not creator_id:
            return ""
        return (
            f"https://{self._partner_domain()}/partner/im?"
            f"creator_id={creator_id}&market={self._market_id()}&enter_from=find_creator_detail"
        )

    @staticmethod
    def _parse_creator_id_from_url(text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        match = re.search(r"cid=(\\d+)", text)
        if match:
            return match.group(1)
        match = re.search(r"creator_id=(\\d+)", text)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _is_partner_home_url(url: str) -> bool:
        if not url:
            return False
        lowered = url.lower()
        return "tiktokshop.com" in lowered and "partner" in lowered and "account/login" not in lowered

    def _build_default_search_strategy(self) -> Dict[str, Any]:
        strategy = {
            "search_keywords": getattr(self.settings, "CREATOR_SEARCH_KEYWORDS", ""),
            "product_category": getattr(self.settings, "CREATOR_PRODUCT_CATEGORY", []),
            "fans_age_range": getattr(self.settings, "CREATOR_FANS_AGE_RANGE", []),
            "fans_gender": getattr(self.settings, "CREATOR_FANS_GENDER", ""),
            "content_type": getattr(self.settings, "CREATOR_CONTENT_TYPE", []),
            "sales": getattr(self.settings, "CREATOR_SALES", []),
            "min_engagement_rate": getattr(
                self.settings, "CREATOR_MIN_ENGAGEMENT_RATE", 0
            ),
            "min_fans": getattr(self.settings, "CREATOR_MIN_FANS", 800),
            "avg_views": getattr(self.settings, "CREATOR_AVG_VIEWS", 800),
            "gmv": getattr(self.settings, "CREATOR_GMV", []),
        }

        strategy_path = getattr(self.settings, "CREATOR_SEARCH_STRATEGY_PATH", None)
        if strategy_path:
            path = Path(strategy_path)
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8") as file:
                        data = json.load(file)
                    if isinstance(data, dict):
                        strategy.update(data.get("search_strategy", data))
                except Exception as exc:
                    self.logger.warning(
                        "Failed to load search strategy file", path=str(path), error=str(exc)
                    )

        strategy_json = getattr(self.settings, "CREATOR_SEARCH_STRATEGY_JSON", None)
        if strategy_json:
            try:
                parsed = json.loads(strategy_json)
                if isinstance(parsed, dict):
                    strategy.update(parsed)
            except Exception as exc:
                self.logger.warning("Failed to parse search strategy JSON", error=str(exc))

        return strategy

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

    def _select_account(self, region: Optional[str], account_name: Optional[str]) -> AccountProfile:
        desired_region = (region or self.default_region or "MX").upper()
        if account_name:
            for account in self.accounts_data:
                if account_name.lower() == str(account.get("name", "")).lower():
                    enabled = account.get("enabled", True)
                    if not enabled:
                        raise PlaywrightError(f"Account {account_name} is disabled")
                    return AccountProfile(
                        name=account.get("name", ""),
                        account_id=str(account.get("id") or account.get("creator_id") or ""),
                        login_email=account.get("login_email", ""),
                        login_password=account.get("login_password"),
                        gmail_username=account.get("gmail_username", ""),
                        gmail_app_password=account.get("gmail_app_password", ""),
                        region=str(account.get("region", desired_region)).upper(),
                        enabled=enabled,
                    )
            raise PlaywrightError(f"Account {account_name} not found in config")

        for account in self.accounts_data:
            account_region = str(account.get("region", "")).upper()
            enabled = account.get("enabled", True)
            if enabled and account_region == desired_region:
                return AccountProfile(
                    name=account.get("name", ""),
                    account_id=str(account.get("id") or account.get("creator_id") or ""),
                    login_email=account.get("login_email", ""),
                    login_password=account.get("login_password"),
                    gmail_username=account.get("gmail_username", ""),
                    gmail_app_password=account.get("gmail_app_password", ""),
                    region=account_region,
                    enabled=enabled,
                )

        for account in self.accounts_data:
            if account.get("enabled", True):
                return AccountProfile(
                    name=account.get("name", ""),
                    account_id=str(account.get("id") or account.get("creator_id") or ""),
                    login_email=account.get("login_email", ""),
                    login_password=account.get("login_password"),
                    gmail_username=account.get("gmail_username", ""),
                    gmail_app_password=account.get("gmail_app_password", ""),
                    region=str(account.get("region", desired_region)).upper(),
                    enabled=True,
                )

        return AccountProfile(
            name="default",
            account_id="",
            login_email=getattr(self.settings, "CREATOR_LOGIN_EMAIL", ""),
            login_password=getattr(self.settings, "CREATOR_LOGIN_PASSWORD", ""),
            gmail_username=getattr(self.settings, "CREATOR_GMAIL_USERNAME", ""),
            gmail_app_password=getattr(self.settings, "CREATOR_GMAIL_APP_PASSWORD", ""),
            region=desired_region,
            enabled=True,
        )

    def resolve_profile(self, region: Optional[str], account_name: Optional[str]) -> AccountProfile:
        return self._select_account(region, account_name)

    async def initialize(self, profile: Optional[AccountProfile] = None) -> None:
        async with self._initialize_lock:
            if self._page and self._context and self._browser:
                return
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context()
            self._context.set_default_timeout(30_000)
            self._page = await self._context.new_page()

            self.account_profile = profile or self.resolve_profile(self.default_region, None)
            self.region = self.account_profile.region
            self.target_url = self._build_creator_url()
            self.db_actor_id = self._derive_db_actor_id(self.account_profile)
            self.gmail_verifier = GmailVerificationCode(
                username=self.account_profile.gmail_username,
                app_password=self.account_profile.gmail_app_password,
            )
            self.logger.info(
                "Playwright session initialized",
                login_email=self.account_profile.login_email,
                region=self.account_profile.region,
                headless=self.headless,
            )

    @staticmethod
    def _derive_db_actor_id(profile: AccountProfile) -> str:
        account_id = (profile.account_id or "").strip()
        if account_id:
            return account_id
        base = (profile.login_email or profile.name or "DEFAULT_ACTOR").strip()
        try:
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, base)).upper()
        except Exception:
            return str(uuid.uuid4()).upper()

    @staticmethod
    def _parse_datetime_value(value: Any) -> Optional[datetime]:
        if value in (None, "", []):
            return None
        if isinstance(value, datetime):
            return value.astimezone().replace(tzinfo=None) if value.tzinfo else value
        text = str(value).strip()
        if not text:
            return None
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return None

    def _derive_run_at_time(self) -> Optional[datetime]:
        metadata = self.task_metadata or {}
        candidates = [
            metadata.get("run_at_time"),
            metadata.get("runAtTime"),
            metadata.get("plan_execute_time"),
            metadata.get("planExecuteTime"),
        ]
        for value in candidates:
            parsed = self._parse_datetime_value(value)
            if parsed:
                return parsed
        return None

    async def _await_run_at_time(self) -> None:
        if not self.plan_execute_time:
            return
        now = datetime.now()
        if self.plan_execute_time <= now:
            return
        wait_seconds = (self.plan_execute_time - now).total_seconds()
        self.logger.info(
            "Waiting for scheduled run time",
            run_at_time=self.plan_execute_time.isoformat(),
            wait_seconds=wait_seconds,
        )
        await asyncio.sleep(wait_seconds)

    @staticmethod
    def _format_duration(seconds: Optional[float]) -> Optional[str]:
        if seconds is None:
            return None
        total = int(max(0, seconds))
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}h{minutes:02d}min{secs:02d}s"

    @staticmethod
    def _format_message_text(subject: str, body: str) -> str:
        subject_clean = (subject or "").replace('"', "").strip()
        body_clean = (body or "").replace("\r\n", "\n")
        body_clean = re.sub(r"\n{3,}", "\n\n", body_clean).strip()
        if subject_clean and body_clean:
            return f"{subject_clean}\n\n{body_clean}"
        return subject_clean or body_clean

    @staticmethod
    def _coerce_flag(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return int(value) != 0
        if isinstance(value, (bytes, bytearray, memoryview)):
            try:
                return int.from_bytes(bytes(value), "big") != 0
            except Exception:
                return False
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y"}:
            return True
        if text in {"0", "false", "no", "n"}:
            return False
        return False

    async def _fetch_creator_history(
        self,
        *,
        creator_name: Optional[str],
        creator_id: Optional[str],
        creator_username: Optional[str],
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        normalized_name = (creator_name or "").strip().lower()
        normalized_username = (creator_username or "").strip().lower()
        conditions = []
        if creator_id:
            conditions.append(CreatorCrawlLogs.platform_creator_id == creator_id)
        if normalized_name:
            conditions.append(
                func.lower(CreatorCrawlLogs.platform_creator_display_name) == normalized_name
            )
            conditions.append(
                func.lower(CreatorCrawlLogs.platform_creator_username) == normalized_name
            )
        if normalized_username:
            conditions.append(
                func.lower(CreatorCrawlLogs.platform_creator_username) == normalized_username
            )

        if not conditions:
            return []

        stmt = (
            select(
                CreatorCrawlLogs.connect,
                CreatorCrawlLogs.reply,
                CreatorCrawlLogs.brand_name,
            )
            .where(or_(*conditions))
            .order_by(CreatorCrawlLogs.creation_time.desc())
            .limit(limit)
        )
        try:
            async with get_db() as session:
                result = await session.execute(stmt)
                rows = result.mappings().all()
        except Exception as exc:
            self.logger.warning("Failed to load creator history", error=str(exc))
            return []

        records: List[Dict[str, Any]] = []
        for row in rows:
            records.append(
                {
                    "connect": self._coerce_flag(row.get("connect")),
                    "reply": self._coerce_flag(row.get("reply")),
                    "brand_name": (row.get("brand_name") or "").strip(),
                }
            )
        return records

    async def _should_send_message(
        self,
        *,
        creator_name: str,
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

    def _resolve_message_text(self, *, connect: bool, reply: bool) -> Optional[str]:
        if reply:
            return None
        if self.only_first == 2:
            if connect and self.later_message_text:
                return self.later_message_text
            return None
        if not connect:
            return self.first_message_text or None
        if self.only_first == 1:
            return None
        return self.later_message_text or self.first_message_text or None

    def _derive_run_deadline(self) -> Optional[datetime]:
        metadata = self.task_metadata or {}
        candidates = [
            metadata.get("run_end_time"),
            metadata.get("runEndTime"),
            metadata.get("plan_stop_time"),
            metadata.get("planStopTime"),
        ]
        for value in candidates:
            parsed = self._parse_datetime_value(value)
            if parsed:
                return parsed
        return None

    def _should_stop(self) -> bool:
        if not self.run_deadline:
            return False
        if datetime.now() >= self.run_deadline:
            self.stop_reason = "run_end_time_reached"
            return True
        return False

    def _build_outreach_task_payload(
        self,
        *,
        status: str,
        message: Optional[str] = None,
        new_creators: Optional[int] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        run_time_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        metadata = self.task_metadata or {}
        brand_meta = metadata.get("brand") if isinstance(metadata.get("brand"), dict) else {}
        search_strategy = metadata.get("search_strategy")
        if not isinstance(search_strategy, dict):
            search_strategy = self.search_strategy or {}

        email_first = metadata.get("email_first")
        if isinstance(email_first, dict):
            email_first_body = email_first.get("email_body") or email_first.get("body")
        elif isinstance(email_first, str):
            email_first_body = email_first
        else:
            email_first_body = metadata.get("email_first_body")

        email_later = metadata.get("email_later")
        if isinstance(email_later, dict):
            email_later_body = email_later.get("email_body") or email_later.get("body")
        elif isinstance(email_later, str):
            email_later_body = email_later
        else:
            email_later_body = metadata.get("email_later_body")

        payload: Dict[str, Any] = {
            "task_id": self.task_id,
            "platform": "tiktok",
            "task_name": metadata.get("task_name"),
            "campaign_id": metadata.get("campaign_id") or metadata.get("platform_campaign_id"),
            "campaign_name": metadata.get("campaign_name") or metadata.get("platform_campaign_name"),
            "product_id": metadata.get("product_id") or metadata.get("platform_product_id"),
            "product_name": metadata.get("product_name") or metadata.get("platform_product_name"),
            "product_list": metadata.get("product_list") or metadata.get("productList"),
            "region": self.region,
            "brand": self.brand_name,
            "only_first": brand_meta.get("only_first", metadata.get("only_first")),
            "task_type": metadata.get("task_type"),
            "status": status,
            "message": message or metadata.get("message"),
            "account_email": self.account_profile.login_email if self.account_profile else None,
            "search_keywords": self.search_keywords_raw,
            "product_category": search_strategy.get("product_category"),
            "fans_age_range": search_strategy.get("fans_age_range"),
            "fans_gender": search_strategy.get("fans_gender"),
            "content_type": search_strategy.get("content_type"),
            "gmv": search_strategy.get("gmv"),
            "sales": search_strategy.get("sales"),
            "min_fans": search_strategy.get("min_fans", self.min_fans if hasattr(self, "min_fans") else None),
            "avg_views": search_strategy.get("avg_views", getattr(self, "avg_views", None)),
            "min_engagement_rate": search_strategy.get(
                "min_engagement_rate", getattr(self, "min_engagement_rate", None)
            ),
            "email_first_body": email_first_body,
            "email_later_body": email_later_body,
            "target_new_creators": metadata.get("target_new_creators"),
            "max_creators": metadata.get("max_creators"),
            "run_at_time": metadata.get("run_at_time") or metadata.get("runAtTime"),
            "run_end_time": (
                metadata.get("run_end_time")
                or metadata.get("runEndTime")
                or (self.run_deadline.isoformat() if self.run_deadline else None)
            ),
            "run_time": self._format_duration(run_time_seconds),
            "new_creators": new_creators,
            "started_at": started_at.isoformat() if started_at else None,
            "finished_at": finished_at.isoformat() if finished_at else None,
            "created_at": metadata.get("created_at"),
        }
        return payload

    async def _sync_outreach_task(
        self,
        *,
        status: str,
        message: Optional[str] = None,
        new_creators: Optional[int] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        run_time_seconds: Optional[float] = None,
    ) -> None:
        if not self.task_id:
            return
        try:
            payload = self._build_outreach_task_payload(
                status=status,
                message=message,
                new_creators=new_creators,
                started_at=started_at,
                finished_at=finished_at,
                run_time_seconds=run_time_seconds,
            )
            await self.outreach_task_client.submit(
                source=self.source,
                operator_id=self.db_actor_id or self.task_id,
                task=payload,
            )
        except Exception as exc:
            self.logger.warning("Failed to sync outreach task", error=str(exc))

    async def _enqueue_outreach_chatbot_task(
        self,
        *,
        creator_data: Dict[str, Any],
    ) -> bool:
        creator_id = str(
            creator_data.get("creator_id")
            or creator_data.get("platform_creator_id")
            or ""
        ).strip()
        if not creator_id:
            self.logger.warning(
                "Skip outreach enqueue: missing creator_id",
                creator_name=creator_data.get("creator_name"),
                creator_username=creator_data.get("creator_username"),
                chat_url=creator_data.get("creator_chaturl"),
            )
            return False

        task = {
            "task_id": str(uuid.uuid4()).upper(),
            "outreach_task_id": self.task_id,
            "region": self.region,
            "platform_creator_id": creator_id,
            "platform_creator_username": creator_data.get(
                "platform_creator_username"
            )
            or creator_data.get("creator_username"),
            "platform_creator_display_name": creator_data.get(
                "platform_creator_display_name"
            )
            or creator_data.get("creator_name"),
            "creator_name": creator_data.get("creator_name"),
            "creator_username": creator_data.get("creator_username"),
            "account_name": self.account_profile.name if self.account_profile else None,
            "operator_id": self.db_actor_id,
            "brand_name": self.brand_name,
            "only_first": self.only_first,
            "task_metadata": dict(self.task_metadata or {}),
        }
        await self.outreach_chatbot_client.submit([task])
        self.logger.info(
            "Outreach task enqueued",
            outreach_task_id=self.task_id,
            creator_id=creator_id,
            creator_name=creator_data.get("creator_name"),
        )
        return True

    async def close(self) -> None:
        if self.ingestion_client:
            await self.ingestion_client.aclose()
        if self.outreach_task_client:
            await self.outreach_task_client.aclose()
        if self.outreach_chatbot_client:
            await self.outreach_chatbot_client.aclose()
        if self.outreach_control_client:
            await self.outreach_control_client.aclose()
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def prewarm(self) -> None:
        async with self._prewarm_lock:
            if self._prewarmed:
                return
            try:
                profile = self.resolve_profile(self.default_region, None)
                await self.initialize(profile)
                if self._page:
                    await self.login(self._page)
                    await self.navigate_to_creator_connection(self._page)
                self._prewarmed = True
            except Exception as exc:
                self.logger.warning("Prewarm failed", error=str(exc), exc_info=True)

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
        path = (urlparse(page.url or "").path or "").lower()
        return "login" not in path

    async def delay(self, seconds: float) -> None:
        if seconds <= 0:
            return
        await asyncio.sleep(seconds)

    async def _dismiss_verify_bar(self, page) -> bool:
        close_selectors = [
            "#verify-bar-close",
            "a.verify-bar-close",
            'a[aria-label="Close"][id="verify-bar-close"]',
        ]
        for selector in close_selectors:
            try:
                close_btn = page.locator(selector).first
                if await close_btn.count() > 0 and await close_btn.is_visible():
                    await close_btn.click(timeout=1000)
                    self.logger.debug("Closed verify bar", selector=selector)
                    await self.delay(0.2)
                    return True
            except Exception:
                continue
        return False

    def _detail_has_value(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    def _detail_data_incomplete(self, creator_data: Optional[Dict[str, Any]]) -> bool:
        if not creator_data:
            return True
        if not self._detail_has_value(creator_data.get("creator_name")):
            return True
        signal_fields = [
            "categories",
            "followers",
            "intro",
            "sales_revenue",
            "sales_units_sold",
            "sales_gpm",
            "sales_revenue_per_buyer",
            "gmv_per_sales_channel",
            "gmv_by_product_category",
            "avg_commission_rate",
            "collab_products",
            "partnered_brands",
            "product_price",
            "video_gpm",
            "videos",
            "avg_video_views",
            "avg_video_engagement_rate",
            "live_gpm",
            "live_streams",
            "avg_live_views",
            "avg_live_engagement_rate",
            "followers_male",
            "followers_female",
            "followers_18_24",
            "followers_25_34",
            "followers_35_44",
            "followers_45_54",
            "followers_55_more",
        ]
        filled = sum(
            1 for field in signal_fields if self._detail_has_value(creator_data.get(field))
        )
        return filled < 2

    async def _refresh_creator_detail(
        self, page, detail_page, creator_name: str, is_new_tab: bool
    ):
        await self._dismiss_verify_bar(detail_page)
        try:
            await detail_page.reload(wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            self.logger.warning(
                "Detail page reload failed", creator_name=creator_name, error=str(exc)
            )
        await self.delay(2)
        await self._dismiss_verify_bar(detail_page)
        if is_new_tab:
            return detail_page, is_new_tab, None
        try:
            await detail_page.wait_for_selector(
                'input[data-tid="m4b_input_search"]', timeout=15000
            )
        except Exception:
            pass
        try:
            refreshed_page, refreshed_is_new_tab, click_creator_id = (
                await self._open_detail_and_get_page(page, creator_name)
            )
            return refreshed_page, refreshed_is_new_tab, click_creator_id
        except Exception as exc:
            self.logger.warning(
                "Detail page reopen failed", creator_name=creator_name, error=str(exc)
            )
        return detail_page, is_new_tab, None

    async def click_blank_area(self, page) -> None:
        try:
            await self._dismiss_verify_bar(page)
            header = page.locator(
                'div.m4b-page-header-title-text:has-text("Find creators")'
            ).first
            if await header.count() > 0 and await header.is_visible():
                await header.click(timeout=2_000)
                self.logger.debug("Clicked blank area (header)")
                await self.delay(0.3)
                return
            point = await page.evaluate(
                """() => {
                const isUnsafe = (el) => {
                    if (!el) return true;
                    const tag = (el.tagName || "").toLowerCase();
                    if (["button", "input", "select", "textarea", "label"].includes(tag)) {
                        return true;
                    }
                    const role = el.getAttribute ? el.getAttribute("role") : "";
                    if (role === "button" || role === "radio") return true;
                    if (el.closest) {
                        if (el.closest("button, input, select, textarea, label")) return true;
                        if (
                            el.closest(
                                "#filter-container, .index-module__searchFilter--Q2AjT, .index-module__filter--CKWIA"
                            )
                        ) {
                            return true;
                        }
                    }
                    return false;
                };
                const points = [
                    [10, 10],
                    [window.innerWidth - 10, 10],
                    [window.innerWidth - 10, window.innerHeight - 10],
                    [10, window.innerHeight - 10],
                    [Math.floor(window.innerWidth / 2), 10],
                ];
                for (const [x, y] of points) {
                    const el = document.elementFromPoint(x, y);
                    if (!isUnsafe(el)) {
                        return { x, y };
                    }
                }
                return { x: 10, y: 10 };
            }"""
            )
            await page.mouse.click(point["x"], point["y"])
            self.logger.debug("Clicked blank area", point=point)
            await self.delay(0.5)
        except Exception as exc:
            self.logger.warning("Failed to click blank area", error=str(exc))

    async def login(self, page) -> bool:
        max_retries = 5
        if not self.account_profile or not self.gmail_verifier:
            raise PlaywrightError("Account profile is not initialized")

        for attempt in range(max_retries):
            self.logger.info("Login attempt", attempt=attempt + 1, max_retries=max_retries)
            try:
                redirect_host = self._partner_domain()
                login_url = (
                    "https://partner-sso.tiktok.com/account/login"
                    "?from=ttspc_logout"
                    f"&redirectURL=%2F%2F{redirect_host}%2Fhome"
                    "&lang=en"
                    "&local_id=localID_Portal_88574979_1758691471679"
                    "&userID=51267627"
                    "&is_through_login=1"
                )
                await page.goto(login_url, wait_until="networkidle")
                if await self._is_logged_in(page):
                    self.logger.info("Already logged in")
                    return True

                email_login_btn = page.get_by_text("Log in with code").first
                await email_login_btn.click()

                await page.fill("#email input", self.account_profile.login_email)

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
                if not verification_code:
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
                    await self.delay(5)
                    return True
                self.logger.error("Login submitted but markers not found")
                await asyncio.sleep(3)
            except Exception as exc:
                self.logger.error("Login attempt failed", error=str(exc))
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)

        self.logger.error("Login failed after retries")
        return False

    async def navigate_to_creator_connection(self, page) -> bool:
        self.logger.info("Navigating to creator connection page")
        try:
            try:
                await page.wait_for_selector(
                    "text=Welcome to TikTok Shop Partner Center", timeout=20000
                )
            except Exception:
                try:
                    await page.wait_for_selector("text=Account GMV trend", timeout=20000)
                except Exception:
                    try:
                        await page.wait_for_selector(
                            "text=View your data and facilitate seller authorizations",
                            timeout=20000,
                        )
                    except Exception:
                        await page.wait_for_selector("text=Hi", timeout=20000)

            await self.click_blank_area(page)

            try:
                creator_button = page.locator(
                    "#root > div > div.index__content--sl5LM.ttspc-row > "
                    "div.index__sideMenu--K7BH0 > div > div.index__menuList--hV6LD > "
                    "div > div:nth-child(3)"
                ).first
                await creator_button.wait_for(state="visible", timeout=10000)
                await creator_button.click()
                self.logger.info("Clicked creator menu via menu list selector")
            except Exception:
                try:
                    creator_button = page.locator('[data-uid="firstmenuitem:div:0912e"]')
                    await creator_button.wait_for(state="visible", timeout=10000)
                    await creator_button.click()
                    self.logger.info("Clicked creator menu via data-uid")
                except Exception:
                    try:
                        creator_button = page.locator(
                            ".index__firstMenuItem--msEti.index__menuClosed--ROED2"
                        ).first
                        await creator_button.wait_for(state="visible", timeout=10000)
                        await creator_button.click()
                        self.logger.info("Clicked creator menu via class")
                    except Exception:
                        try:
                            creator_button = (
                                page.locator("svg.arco-icon-creator_marketplace_unselect")
                                .locator("..")
                                .locator("..")
                            )
                            await creator_button.wait_for(state="visible", timeout=10000)
                            await creator_button.click()
                            self.logger.info("Clicked creator menu via svg parent")
                        except Exception:
                            creator_button = page.locator(
                                ".index__firstMenuItem--msEti:has(svg.arco-icon-creator_marketplace_unselect)"
                            )
                            await creator_button.wait_for(state="visible", timeout=10000)
                            await creator_button.click()
                            self.logger.info("Clicked creator menu via has()")

            if self._normalized_region() == "ES":
                self.logger.info(
                    "ES region detected; waiting and redirecting to creator page",
                    target_url=self.target_url,
                )
                await self.delay(5)
                await page.goto(self.target_url, wait_until="networkidle", timeout=60000)
            else:
                await self.delay(8)
            await page.wait_for_selector("text=Find creators", timeout=60000)
            self.logger.info("Creator page loaded")
            return True
        except PlaywrightTimeoutError:
            self.logger.error("Creator page not loaded within timeout")
            return False
        except Exception as exc:
            self.logger.error("Failed to navigate to creator page", error=str(exc))
            return False

    def parse_search_strategy(self) -> None:
        strategy = self.search_strategy or {}

        keywords = strategy.get("search_keywords", "")
        if isinstance(keywords, str):
            self.search_keywords_raw = keywords.strip()
            self.search_keyword = (
                keywords.split(",")[0].strip() if keywords.strip() else ""
            )
        else:
            self.search_keywords_raw = ", ".join(
                str(key).strip() for key in (keywords or [])
            )
            self.search_keyword = keywords[0].strip() if keywords else ""

        raw_product_cat = strategy.get("product_category", "")
        if isinstance(raw_product_cat, str):
            product_cat_list = [cat.strip() for cat in raw_product_cat.split(",") if cat.strip()]
        elif isinstance(raw_product_cat, list):
            product_cat_list = [str(cat).strip() for cat in raw_product_cat if str(cat).strip()]
        else:
            product_cat_list = []

        normalized_categories: List[str] = []
        normalized_category_ids: List[str] = []

        for entry in product_cat_list:
            key = entry.strip()
            if not key:
                continue

            name = None
            cat_id = None

            if key in CATEGORY_NAME_TO_ID:
                name = key
                cat_id = CATEGORY_NAME_TO_ID[key]
            else:
                lower_key = key.lower()
                if lower_key in CATEGORY_NAME_TO_ID_LOWER:
                    name = next(
                        original_name
                        for original_name, code in CATEGORY_NAME_TO_ID.items()
                        if original_name.lower() == lower_key
                    )
                    cat_id = CATEGORY_NAME_TO_ID[name]
                elif key in CATEGORY_ID_TO_NAME:
                    cat_id = key
                    name = CATEGORY_ID_TO_NAME[key]
                else:
                    self.logger.warning("Unknown product category", category=key)
                    continue

            normalized_categories.append(name)
            normalized_category_ids.append(cat_id)

        self.product_categories = normalized_categories
        self.product_category_ids = normalized_category_ids
        if normalized_categories:
            self.search_strategy["product_category"] = normalized_categories
            self.search_strategy["product_category_ids"] = normalized_category_ids
        else:
            self.product_categories = []
            self.product_category_ids = []

        def _normalize_age_label(value: Any) -> str:
            text = str(value).strip()
            if not text:
                return ""
            text = (
                text.replace("—", "-")
                .replace("–", "-")
                .replace("~", "-")
                .replace(" to ", "-")
                .replace("TO", "-")
            )
            compact = text.replace(" ", "")
            if compact.endswith("+"):
                return compact.replace("++", "+")
            if "-" in compact:
                parts = [p for p in compact.split("-") if p]
                if len(parts) >= 2:
                    return f"{parts[0]}-{parts[1]}"
            return compact

        age_range = strategy.get("fans_age_range", [])
        if isinstance(age_range, str):
            if age_range.strip() == "":
                self.age_ranges = []
            else:
                self.age_ranges = [
                    normalized
                    for age in age_range.split(",")
                    if (normalized := _normalize_age_label(age))
                ]
        elif isinstance(age_range, list):
            self.age_ranges = [
                normalized
                for age in age_range
                if (normalized := _normalize_age_label(age))
            ]
        else:
            self.age_ranges = []

        gender_info = strategy.get("fans_gender", "")
        if isinstance(gender_info, dict):
            gender_info = (
                gender_info.get("raw")
                or gender_info.get("value")
                or gender_info.get("label")
                or ""
            )
        if isinstance(gender_info, str):
            text = gender_info.strip()
            if not text:
                self.gender, self.gender_percentage = "", None
            else:
                match = re.search(r"(\d+)%", text)
                pct = int(match.group(1)) if match else 50
                if "female" in text.lower():
                    self.gender, self.gender_percentage = "Female", pct
                elif "male" in text.lower():
                    self.gender, self.gender_percentage = "Male", pct
                else:
                    self.gender, self.gender_percentage = "", None
        else:
            self.gender, self.gender_percentage = "", None

        self.min_fans = int(strategy.get("min_fans", 5000))

        content = strategy.get("content_type", [])
        if isinstance(content, str):
            self.content_types = [content.strip()] if content.strip() else []
        elif isinstance(content, list):
            self.content_types = [str(item).strip() for item in content if str(item).strip()]
        else:
            self.content_types = []

        def _parse_gmv_value(value, default=None):
            if value in (None, "", []):
                return default
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                cleaned = (
                    value.replace("$", "")
                    .replace("\u20ac", "")
                    .replace("\u00a3", "")
                    .replace(",", "")
                    .replace(" ", "")
                )
                if "." in cleaned:
                    parts = cleaned.split(".")
                    if (
                        len(parts) > 1
                        and all(part.isdigit() for part in parts)
                        and all(len(part) == 3 for part in parts[1:])
                    ):
                        cleaned = "".join(parts)
                if cleaned.upper().endswith("K"):
                    try:
                        return float(cleaned[:-1]) * 1000
                    except ValueError:
                        pass
                try:
                    return float(cleaned)
                except ValueError:
                    match = re.search(r"(\d+)", cleaned)
                    if match:
                        return float(match.group(1))
            return default

        gmv_code_definitions = [
            {
                "code": "0-100",
                "lower": 0,
                "upper": 100,
                "label_fr": "0 EUR-100 EUR",
                "label_default": "$0-$100",
            },
            {
                "code": "100-1k",
                "lower": 100,
                "upper": 1000,
                "label_fr": "100 EUR-1,000 EUR",
                "label_default": "$100-$1K",
            },
            {
                "code": "1k-10k",
                "lower": 1000,
                "upper": 10000,
                "label_fr": "1,000 EUR-10K EUR",
                "label_default": "$1K-$10K",
            },
            {
                "code": "10k+",
                "lower": 10000,
                "upper": None,
                "label_fr": "10K EUR+",
                "label_default": "$10K+",
            },
        ]

        def _label_for_code(code: str) -> Optional[str]:
            for entry in gmv_code_definitions:
                if entry["code"] == code:
                    return entry["label_fr"] if self.region == "FR" else entry["label_default"]
            return None

        def _normalize_gmv_code(code) -> Optional[str]:
            if code in (None, "", []):
                return None
            text = str(code).strip().lower()
            text = (
                text.replace("$", "")
                .replace("\u20ac", "")
                .replace("usd", "")
                .replace("eur", "")
                .replace("\u2013", "-")
                .replace("\u2014", "-")
                .replace("_", "-")
                .replace("to", "-")
                .replace(" ", "")
            )
            text = text.replace(",", "").replace(".", "")
            if text.endswith("plus"):
                text = text[:-4] + "+"
            if text in {"0-100", "0-100+", "0-100k"}:
                return "0-100"
            if text in {"100-1k", "100-1000", "100-1k+", "100-1000+"}:
                return "100-1k"
            if text in {"1k-10k", "1000-10000", "1000-10k", "1k-10000"}:
                return "1k-10k"
            if text in {"10k+", "10000+", "10k", "10000"}:
                return "10k+"
            return None

        gmv_codes_input = strategy.get("gmv", [])
        if isinstance(gmv_codes_input, str):
            gmv_codes_input = [gmv_codes_input]

        normalized_codes: List[str] = []
        if isinstance(gmv_codes_input, (list, tuple)):
            for code in gmv_codes_input:
                norm = _normalize_gmv_code(code)
                if norm and norm not in normalized_codes:
                    normalized_codes.append(norm)

        if normalized_codes:
            self.gmv_ranges = [
                label for code in normalized_codes if (label := _label_for_code(code))
            ]
            self.search_strategy["gmv"] = normalized_codes
        else:
            min_gmv = _parse_gmv_value(strategy.get("min_GMV"), default=0)
            max_gmv = _parse_gmv_value(strategy.get("max_GMV"), default=None)

            if max_gmv is not None and max_gmv < min_gmv:
                max_gmv = min_gmv

            epsilon = 1e-6

            def _locate_index(value):
                if value is None:
                    return 0
                for idx, entry in enumerate(gmv_code_definitions):
                    lower = entry["lower"]
                    upper = entry["upper"]
                    if value + epsilon < lower:
                        continue
                    if upper is None:
                        return idx
                    if value < upper - epsilon:
                        return idx
                return len(gmv_code_definitions) - 1

            start_idx = _locate_index(min_gmv)
            end_idx = (
                len(gmv_code_definitions) - 1
                if max_gmv is None
                else _locate_index(max_gmv)
            )
            if end_idx < start_idx:
                end_idx = start_idx

            selected_entries = gmv_code_definitions[start_idx : end_idx + 1]
            self.gmv_ranges = [
                entry["label_fr"] if self.region == "FR" else entry["label_default"]
                for entry in selected_entries
            ]
            normalized_codes = [entry["code"] for entry in selected_entries]
            self.search_strategy["gmv"] = normalized_codes

        self.gmv_ranges = self.gmv_ranges or []

        sales_code_definitions = [
            {"code": "0-10", "lower": 0, "upper": 10, "label": "0-10"},
            {"code": "10-100", "lower": 10, "upper": 100, "label": "10-100"},
            {"code": "100-1k", "lower": 100, "upper": 1000, "label": "100-1K"},
            {"code": "1k+", "lower": 1000, "upper": None, "label": "1K+"},
        ]
        label_map = {entry["code"]: entry["label"] for entry in sales_code_definitions}

        def _normalize_sales_code(code) -> Optional[str]:
            if code in (None, "", []):
                return None
            text = str(code).strip().lower()
            text = (
                text.replace(" ", "")
                .replace("\u2013", "-")
                .replace("\u2014", "-")
                .replace("to", "-")
                .replace("_", "-")
                .replace("plus", "+")
            )
            text = text.replace(",", "")
            if text in {"0-10", "0_10"}:
                return "0-10"
            if text in {"10-100", "10_100"}:
                return "10-100"
            if text in {"100-1k", "100-1000", "100-1k+", "100_1k"}:
                return "100-1k"
            if text in {"1k+", "1000+", "1k", "1000"}:
                return "1k+"
            return None

        def _extract_numeric_threshold(value) -> Optional[int]:
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                match = re.search(r"(\d+)", value)
                if match:
                    return int(match.group(1))
            return None

        def _codes_from_threshold(threshold: int) -> List[str]:
            if threshold <= 0:
                return [entry["code"] for entry in sales_code_definitions]
            if threshold <= 10:
                return [entry["code"] for entry in sales_code_definitions[1:]]
            if threshold <= 100:
                return [entry["code"] for entry in sales_code_definitions[2:]]
            if threshold <= 1000:
                return [sales_code_definitions[3]["code"]]
            return []

        def _normalize_sales_input(raw) -> List[str]:
            if raw in (None, "", []):
                return []
            items = list(raw) if isinstance(raw, (list, tuple)) else [raw]

            codes: List[str] = []
            thresholds: List[int] = []

            for item in items:
                if item in (None, "", []):
                    continue
                normalized_code = _normalize_sales_code(item)
                if normalized_code:
                    if normalized_code not in codes:
                        codes.append(normalized_code)
                    continue
                threshold = _extract_numeric_threshold(item)
                if threshold is not None:
                    thresholds.append(threshold)

            if not codes and thresholds:
                threshold = min(thresholds)
                for code in _codes_from_threshold(threshold):
                    if code not in codes:
                        codes.append(code)
            return codes

        sales_field_specified = "sales" in strategy
        legacy_sales_specified = "min_sales" in strategy

        normalized_sales_codes = _normalize_sales_input(
            strategy.get("sales") if sales_field_specified else None
        )

        if not normalized_sales_codes and not sales_field_specified:
            normalized_sales_codes = _normalize_sales_input(
                strategy.get("min_sales") if legacy_sales_specified else None
            )
            if not normalized_sales_codes and not legacy_sales_specified:
                normalized_sales_codes = _codes_from_threshold(10)

        normalized_sales_codes = [
            code for code in normalized_sales_codes if code in label_map
        ]
        self.sales_ranges = [label_map[code] for code in normalized_sales_codes]
        self.search_strategy["sales"] = normalized_sales_codes
        self.sales_ranges = self.sales_ranges or []

        self.avg_views = int(strategy.get("avg_views", 5000))

        engagement = strategy.get("min_engagement_rate")
        if engagement in (None, "", []):
            self.min_engagement_rate = 0.0
        else:
            try:
                self.min_engagement_rate = float(engagement)
            except (TypeError, ValueError):
                try:
                    self.min_engagement_rate = float(str(engagement).replace("%", ""))
                except (TypeError, ValueError):
                    self.min_engagement_rate = 0.0

        self.logger.info(
            "Parsed search strategy",
            keyword=self.search_keyword,
            product_categories=self.product_categories,
            age_ranges=self.age_ranges,
            gender=self.gender,
            gender_percentage=self.gender_percentage,
            min_fans=self.min_fans,
            content_types=self.content_types,
            gmv_ranges=self.gmv_ranges,
            sales_ranges=self.sales_ranges,
            avg_views=self.avg_views,
            min_engagement_rate=self.min_engagement_rate,
        )

    async def _select_product_category(
        self, page, category_name: str, category_id: Optional[str]
    ) -> str:
        if category_id:
            try:
                result = await page.evaluate(
                    """(cid) => {
                    const input = document.querySelector(`input[type="checkbox"][value="${cid}"]`);
                    if (!input) return "not_found";
                    if (input.checked) return "already_checked";
                    const label = input.closest("label");
                    if (label) {
                        const mask = label.querySelector(".arco-checkbox-mask");
                        (mask || input).click();
                    } else {
                        input.click();
                    }
                    return "clicked";
                }""",
                    category_id,
                )
                if result in ("clicked", "already_checked"):
                    return result
            except Exception:
                pass

        selectors = [
            f'li:has-text("{category_name}") input[type="checkbox"]',
            f'li:has-text("{category_name}") .arco-checkbox-mask',
            f'li:has-text("{category_name}") .arco-checkbox-icon-hover',
            f'label:has-text("{category_name}") input[type="checkbox"]',
        ]

        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() == 0:
                    continue
                try:
                    await locator.scroll_into_view_if_needed(timeout=800)
                except Exception:
                    pass

                try:
                    if await locator.is_checked():
                        return "already_checked"
                except Exception:
                    pass

                await locator.click(force=True, timeout=3000)
                return "clicked"
            except Exception:
                continue
        return "not_found"

    async def _extract_creator_id_from_dom(self, page) -> Optional[str]:
        try:
            return await page.evaluate(
                """() => {
                const ids = new Set();
                const sources = [];
                try {
                    sources.push(window.location.href || "");
                    sources.push(document.URL || "");
                } catch (e) {}
                const add = (val) => {
                    if (!val) return;
                    const text = String(val);
                    const patterns = [
                        /cid\\s*[:=]\\s*\"?(\\d{5,})\"?/,
                        /creator_id\\s*[:=]\\s*\"?(\\d{5,})\"?/,
                        /(?:creator_id|cid)=?(\\d{5,})/,
                    ];
                    for (const pattern of patterns) {
                        const match = text.match(pattern);
                        if (match) {
                            ids.add(match[1]);
                            break;
                        }
                    }
                };
                document.querySelectorAll('[href]').forEach((el) => add(el.getAttribute('href')));
                document
                    .querySelectorAll('[data-creator-id],[data-creatorid],[data-id]')
                    .forEach((el) => {
                        add(el.getAttribute('data-creator-id'));
                        add(el.getAttribute('data-creatorid'));
                        add(el.getAttribute('data-id'));
                    });
                const html = document.documentElement && document.documentElement.innerHTML;
                if (html) sources.push(html);
                try {
                    if (window.__NEXT_DATA__) sources.push(JSON.stringify(window.__NEXT_DATA__));
                    if (window.__NUXT__) sources.push(JSON.stringify(window.__NUXT__));
                    if (window.__INITIAL_STATE__) sources.push(JSON.stringify(window.__INITIAL_STATE__));
                    if (window.__APOLLO_STATE__) sources.push(JSON.stringify(window.__APOLLO_STATE__));
                } catch (e) {}
                sources.forEach(add);
                return Array.from(ids)[0] || null;
            }"""
            )
        except Exception:
            return None

    async def _extract_creator_id_from_list(
        self, page, creator_name: str
    ) -> Optional[str]:
        if not creator_name:
            return None
        try:
            return await page.evaluate(
                """(name) => {
                const matchCid = (text) => {
                    if (!text) return null;
                    const m = String(text).match(/cid=(\\d{5,})/);
                    return m ? m[1] : null;
                };
                const spans = Array.from(document.querySelectorAll("span"))
                    .filter((el) => (el.textContent || "").trim() === name);
                for (const span of spans) {
                    let node = span;
                    for (let i = 0; i < 6 && node; i += 1, node = node.parentElement) {
                        const link = node.querySelector && node.querySelector('a[href*="cid="]');
                        if (link) {
                            const cid = matchCid(link.getAttribute("href"));
                            if (cid) return cid;
                        }
                        if (node.getAttribute) {
                            const cid = matchCid(node.getAttribute("data-href"));
                            if (cid) return cid;
                        }
                        if (node.outerHTML) {
                            const cid = matchCid(node.outerHTML);
                            if (cid) return cid;
                        }
                    }
                }
                return null;
            }""",
                creator_name,
            )
        except Exception:
            return None

    async def search_and_filter(self, page, search_keyword: Optional[str] = None) -> bool:
        if search_keyword is None:
            search_keyword = self.search_keyword

        self.logger.info(
            "Starting search and filter",
            keyword=search_keyword,
            strategy=self.search_strategy,
        )

        applied = {
            "keyword": None,
            "creators": {"product_category": [], "content_type": []},
            "followers": {
                "age": [],
                "follower_min": None,
                "gender": None,
                "gender_percentage": None,
            },
            "performance": {
                "gmv": [],
                "items_sold": [],
                "avg_views_min": None,
                "engagement_min": None,
            },
        }

        async def _click_button_by_text(texts: list) -> bool:
            if not texts:
                return False
            try:
                return await page.evaluate(
                    """(candidates) => {
                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (style.display === "none" || style.visibility === "hidden") return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    const buttons = Array.from(document.querySelectorAll("button"));
                    for (const text of candidates) {
                        if (!text) continue;
                        const btn = buttons.find(
                            (b) => (b.textContent || "").includes(text) && isVisible(b)
                        );
                        if (btn) {
                            btn.scrollIntoView({ block: "center" });
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                    texts,
                )
            except Exception:
                return False

        async def _visible_popup_root() -> Optional[str]:
            try:
                return await page.evaluate(
                    """() => {
                    const popup = Array.from(document.querySelectorAll('div[id^="arco-select-popup"]'))
                        .find((el) => !el.style || !String(el.style.display || "").includes("none"));
                    return popup ? `#${popup.id}` : null;
                }"""
                )
            except Exception:
                return None

        async def click_first(
            locators: list,
            desc: str,
            timeout: int = 15000,
            allow_related: bool = True,
        ) -> bool:
            for selector in locators:
                try:
                    locator = page.locator(selector)
                    el = await _pick_visible(locator)
                    if el and await el.is_enabled():
                        try:
                            await el.scroll_into_view_if_needed(timeout=1500)
                        except Exception:
                            pass
                        await el.click(timeout=timeout, force=True)
                        self.logger.debug("Click succeeded", target=desc, selector=selector)
                        return True
                except Exception as exc:
                    self.logger.debug(
                        "Click attempt failed",
                        target=desc,
                        selector=selector,
                        error=str(exc),
                    )
            candidates = [desc]
            if allow_related:
                if "Content" in desc:
                    candidates.append("Content type")
                if "Follower" in desc:
                    candidates.extend(["Follower age", "Follower size", "Follower count"])
            if await _click_button_by_text(candidates):
                self.logger.debug("Click succeeded (js)", target=desc)
                return True
            self.logger.warning("Click target not found", target=desc)
            return False

        async def _dismiss_interceptors() -> None:
            close_selectors = [
                "#verify-bar-close",
                "a.verify-bar-close",
                'a[aria-label="Close"][id="verify-bar-close"]',
            ]
            for selector in close_selectors:
                try:
                    close_btn = page.locator(selector).first
                    if await close_btn.is_visible():
                        await close_btn.click(timeout=1000)
                        await self.delay(0.2)
                        return
                except Exception:
                    continue
            overlay_selectors = [
                'text="Creator Connect Updated"',
                '[class*="arco-message"]',
                '[class*="arco-notification"]',
            ]
            for selector in overlay_selectors:
                try:
                    overlay = page.locator(selector).first
                    if await overlay.is_visible():
                        try:
                            await page.keyboard.press("Escape")
                        except Exception:
                            pass
                        await self.click_blank_area(page)
                        try:
                            await overlay.wait_for(state="hidden", timeout=2000)
                        except Exception:
                            pass
                        return
                except Exception:
                    continue

        async def _force_fill(locator, value: str, timeout: int) -> None:
            try:
                await locator.fill(str(value), timeout=timeout)
                return
            except Exception:
                pass
            try:
                await locator.evaluate(
                    "(el, val) => {"
                    "  el.focus();"
                    "  el.value = val;"
                    "  el.dispatchEvent(new Event('input', { bubbles: true }));"
                    "  el.dispatchEvent(new Event('change', { bubbles: true }));"
                    "}",
                    str(value),
                )
            except Exception:
                raise

        async def fill_first(locators: list, value: str, desc: str, timeout: int = 8000) -> bool:
            for selector in locators:
                try:
                    locator = page.locator(selector)
                    ipt = await _pick_visible(locator)
                    if ipt and await ipt.is_enabled():
                        try:
                            await ipt.scroll_into_view_if_needed(timeout=1500)
                        except Exception:
                            pass
                        try:
                            await _force_fill(ipt, value, timeout)
                        except Exception:
                            await _dismiss_interceptors()
                            await ipt.click(timeout=timeout, force=True)
                            await _force_fill(ipt, value, timeout)
                        self.logger.debug("Filled input", target=desc, value=value, selector=selector)
                        return True
                except Exception as exc:
                    self.logger.debug(
                        "Fill attempt failed",
                        target=desc,
                        selector=selector,
                        error=str(exc),
                    )
            self.logger.warning("Input target not found", target=desc)
            return False

        async def _click_dropdown_by_text(texts: list) -> bool:
            if not texts:
                return False
            try:
                return await page.evaluate(
                    """(candidates) => {
                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (style.display === "none" || style.visibility === "hidden") return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    const buttons = Array.from(document.querySelectorAll("button"));
                    for (const text of candidates) {
                        if (!text) continue;
                        const btn = buttons.find((b) =>
                            (b.textContent || "").includes(text) && isVisible(b)
                        );
                        if (btn) {
                            btn.scrollIntoView({ block: "center" });
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                    texts,
                )
            except Exception:
                return False

        async def open_dropdown(locators: list, desc: str) -> bool:
            for selector in locators:
                try:
                    locator = page.locator(selector)
                    el = await _pick_visible(locator)
                    if not el:
                        continue
                    try:
                        await el.scroll_into_view_if_needed(timeout=1500)
                    except Exception:
                        pass
                    await el.click(timeout=5000, force=True)
                    self.logger.debug("Opened dropdown", target=desc, selector=selector)
                    popup = page.locator(
                        'xpath=//div[starts-with(@id,"arco-select-popup") and not(contains(@style,"display: none"))]'
                    ).first
                    await popup.wait_for(state="visible", timeout=5000)
                    return True
                except Exception as exc:
                    self.logger.debug(
                        "Open dropdown failed",
                        target=desc,
                        selector=selector,
                        error=str(exc),
                    )
            candidates = [desc]
            if "gender" in desc.lower():
                candidates.extend(["Follower gend", "Gender"])
            if "age" in desc.lower():
                candidates.extend(["Follower age", "Age"])
            if await _click_dropdown_by_text(candidates):
                popup = page.locator(
                    'xpath=//div[starts-with(@id,"arco-select-popup") and not(contains(@style,"display: none"))]'
                ).first
                try:
                    await popup.wait_for(state="visible", timeout=5000)
                    self.logger.debug("Opened dropdown (js)", target=desc)
                    return True
                except Exception:
                    pass
            self.logger.warning("Dropdown not found", target=desc)
            return False

        async def _scroll_filter_panel() -> None:
            try:
                await page.evaluate(
                    """() => {
                    const selectors = [
                        "#filter-container",
                        "#content-container",
                        '[class*="filter"]',
                        '[class*="Filter"]'
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            el.scrollIntoView({ block: "start" });
                            try { el.scrollTop = 0; } catch (e) {}
                            return true;
                        }
                    }
                    window.scrollTo(0, 0);
                    return false;
                }"""
                )
            except Exception:
                return

        def _expand_option_variants(text: str) -> List[str]:
            base = str(text).strip()
            if not base:
                return []
            variants = [base]
            if "-" in base:
                variants.append(base.replace(" - ", "-"))
                variants.append(base.replace("-", " - "))
            if "+" in base:
                variants.append(base.replace(" +", "+"))
                variants.append(base.replace("+", " +"))
            seen = set()
            deduped = []
            for item in variants:
                key = item.strip()
                if key and key not in seen:
                    seen.add(key)
                    deduped.append(key)
            return deduped

        async def select_options_in_visible_popup(option_texts: list) -> list:
            chosen = []
            popup_root = await _visible_popup_root()
            for text in option_texts:
                if text is None or str(text).strip() == "":
                    continue
                try:
                    variants = _expand_option_variants(text)
                    selectors = []
                    for variant in variants:
                        if popup_root:
                            selectors.extend(
                                [
                                    f'{popup_root} li[role="option"].arco-select-option-wrapper:has(span.arco-select-option:has-text("{variant}"))',
                                    f'{popup_root} li[role="option"].arco-select-option-wrapper:has(span:has-text("{variant}"))',
                                    f'{popup_root} li[role="option"].arco-select-option.m4b-select-option:has-text("{variant}")',
                                    f'{popup_root} li[role="option"].arco-select-option:has-text("{variant}")',
                                    f'{popup_root} li:has-text("{variant}")',
                                ]
                            )
                        selectors.extend([
                            "xpath=//li[@role=\"option\" and contains(@class, \"arco-select-option\")][.//text()[contains(normalize-space(.), \"%s\")]]"
                            % variant,
                            "xpath=//li[.//label[contains(normalize-space(.), \"%s\")]]/label"
                            % variant,
                            "xpath=//li[.//span[contains(normalize-space(.), \"%s\")]]"
                            % variant,
                            f'li:has-text("{variant}") label',
                            f'li:has-text("{variant}")',
                        ])
                    option = None
                    for selector in selectors:
                        candidate = page.locator(selector).first
                        if await candidate.count() > 0 and await candidate.is_visible():
                            option = candidate
                            break
                    if option:
                        try:
                            await option.scroll_into_view_if_needed(timeout=800)
                        except Exception:
                            pass
                        await option.click(force=True, timeout=3000)
                        self.logger.info("Selected option", option=text)
                        chosen.append(str(text).strip())
                        await self.delay(0.2)
                    else:
                        self.logger.warning("Option not found", option=text)
                except Exception as exc:
                    self.logger.warning("Option selection failed", option=text, error=str(exc))
            return chosen

        async def _pick_visible(locator):
            try:
                count = await locator.count()
            except Exception:
                return None
            if count <= 0:
                return None
            for idx in range(count):
                candidate = locator.nth(idx)
                try:
                    if await candidate.is_visible():
                        return candidate
                except Exception:
                    continue
            return None

        async def wait_spinner_done(max_ms: int = 15000) -> None:
            try:
                await page.locator(
                    '[class*="arco-spin"], [class*="arco-spin-loading"]'
                ).wait_for(state="hidden", timeout=max_ms)
            except Exception:
                return

        async def ensure_panel_active(panel_name: str, panel_selectors: list) -> bool:
            self.logger.info("Ensuring panel active", panel=panel_name)
            await _scroll_filter_panel()
            return await click_first(
                panel_selectors,
                panel_name,
                allow_related=False,
            )

        async def _wait_for_followers_filters(timeout_ms: int = 2000) -> bool:
            await _scroll_filter_panel()
            candidates = [
                "#followerAge button",
                "#followerGender button",
                "#followerSize input",
                'button:has-text("Follower age")',
                'button:has-text("Follower gender")',
                'button:has-text("Follower count")',
            ]
            for selector in candidates:
                try:
                    await page.locator(selector).first.wait_for(
                        state="visible", timeout=timeout_ms
                    )
                    return True
                except Exception:
                    continue
            return False

        async def _followers_panel_active() -> bool:
            return await _wait_for_followers_filters(timeout_ms=500)

        async def _open_followers_panel() -> bool:
            await self.click_blank_area(page)
            await _dismiss_interceptors()
            await _scroll_filter_panel()
            if await _followers_panel_active():
                return await _wait_for_followers_filters()
            selectors = [
                '#submodule_layout_container_id .index-module__searchFilter--Q2AjT .index-module__filter--CKWIA '
                'div.arco-space.mb-16 > div:nth-child(2) button.m4b-button:has(span:has-text("Follower")):visible',
                '#submodule_layout_container_id .index-module__searchFilter--Q2AjT .index-module__filter--CKWIA '
                'div.arco-space.mb-16 > div:nth-child(2) button.m4b-button:has(span:has-text("Followers")):visible',
                '#submodule_layout_container_id .index-module__searchFilter--Q2AjT button[data-e2e="e9e98bcf-9e15-8681"]:visible',
                '#submodule_layout_container_id .index-module__searchFilter--Q2AjT button:has(span:has-text("Follower")):visible',
                '#submodule_layout_container_id .index-module__searchFilter--Q2AjT button:has(span:has-text("Followers")):visible',
                '#submodule_layout_container_id label:has-text("Follower") button:visible',
                '#submodule_layout_container_id label:has-text("Followers") button:visible',
                'button[data-e2e="e9e98bcf-9e15-8681"]:visible',
                'button[data-tid="m4b_button"]:has(span:has-text("Follower")):visible',
                'button[data-tid="m4b_button"]:has(span:has-text("Followers")):visible',
                'button:has-text("Follower"):visible',
                'button:has-text("Followers"):visible',
            ]
            if await click_first(selectors, "Followers", allow_related=False):
                return await _wait_for_followers_filters()
            if await _click_button_by_text(["Followers", "Follower"]):
                return await _wait_for_followers_filters()
            return False

        try:
            await self.click_blank_area(page)

            self.logger.info("Step 1: fill search keyword")
            search_inputs = [
                'input[data-tid="m4b_input_search"]',
                'input[placeholder*="Search"]',
                'input[placeholder*="names"]',
                'xpath=//*[@id="content-container"]//span/span/input',
            ]
            if not await fill_first(search_inputs, search_keyword, "search keyword"):
                return False
            applied["keyword"] = search_keyword

            creators_panel_selectors = [
                'label:has(input[value="creator"]) button',
                'input[value="creator"] ~ button',
            ]
            await self.click_blank_area(page)

            if self.product_categories:
                self.logger.info(
                    "Step 2.1: product categories", categories=self.product_categories
                )
                for idx, (category_name, category_id) in enumerate(
                    zip(self.product_categories, self.product_category_ids), start=1
                ):
                    category_clean = category_name.strip()
                    value = category_id or CATEGORY_NAME_TO_ID.get(category_clean)

                    if not value:
                        self.logger.warning("Unknown product category", category=category_clean)
                        continue

                    self.logger.info("Product category", index=idx, category=category_clean)
                    success = False

                    for attempt in range(3):
                        await ensure_panel_active("Creators", creators_panel_selectors)
                        await self.delay(1)

                        try:
                            opened = await _click_button_by_text(
                                ["Product category", "Product categories", "Category"]
                            )
                            if opened:
                                await self.delay(1)
                            direct_result = await self._select_product_category(
                                page, category_clean, value
                            )
                            if direct_result in ("clicked", "already_checked"):
                                self.logger.info(
                                    "Category selected (direct)",
                                    category=category_clean,
                                    result=direct_result,
                                )
                                applied["creators"]["product_category"].append(
                                    category_clean
                                )
                                success = True
                                break

                            product_cat_selectors = [
                                'button:has(div:has-text("Product category"))',
                                'button:has(div:has-text("Product categories"))',
                                'button:has(div:has-text("Category"))',
                            ]
                            product_cat_btn = None
                            for selector in product_cat_selectors:
                                candidate = await _pick_visible(page.locator(selector))
                                if candidate:
                                    product_cat_btn = candidate
                                    break
                            if product_cat_btn:
                                try:
                                    await product_cat_btn.scroll_into_view_if_needed(timeout=1500)
                                except Exception:
                                    pass
                                await product_cat_btn.click(timeout=5000, force=True)
                                await self.delay(1)

                                try:
                                    await page.locator("ul.arco-cascader-list").first.wait_for(
                                        state="visible", timeout=5000
                                    )
                                except Exception:
                                    self.logger.warning("Cascader popup not visible; retrying")
                                    await self.click_blank_area(page)
                                    await self.delay(1)
                                    continue

                                result = await self._select_product_category(
                                    page, category_clean, value
                                )
                                if result == "clicked":
                                    self.logger.info("Category selected", category=category_clean)
                                    applied["creators"]["product_category"].append(
                                        category_clean
                                    )
                                    success = True
                                    await self.delay(1)
                                    break
                                if result == "already_checked":
                                    self.logger.info(
                                        "Category already selected", category=category_clean
                                    )
                                    applied["creators"]["product_category"].append(
                                        category_clean
                                    )
                                    success = True
                                    break
                                self.logger.warning("Category checkbox not found", category=category_clean)
                            else:
                                self.logger.warning(
                                    "Product category button not found",
                                    category=category_clean,
                                )
                        except Exception as exc:
                            self.logger.warning(
                                "Category selection failed",
                                category=category_clean,
                                attempt=attempt + 1,
                                error=str(exc),
                            )

                        if not success:
                            await self.click_blank_area(page)
                            await self.delay(1)

                    if not success:
                        self.logger.error("Failed to select category", category=category_clean)
                    await self.click_blank_area(page)
            else:
                self.logger.info("Skip product category filter (empty)")

            await self.click_blank_area(page)

            if self.content_types:
                normalized_content = {
                    str(item).strip().lower()
                    for item in self.content_types
                    if str(item).strip()
                }
                if normalized_content == {"video", "live"}:
                    self.logger.info(
                        "Skip content type filter (default video + live)",
                        content_types=self.content_types,
                    )
                else:
                    self.logger.info(
                        "Step 2.3: content types", content_types=self.content_types
                    )
                    for content_type in self.content_types:
                        await ensure_panel_active("Creators", creators_panel_selectors)
                        clicked = await click_first(
                            [
                                'button:has(div:has-text("Content"))',
                                'button:has-text("Content type")',
                                'xpath=//button[.//div[contains(@class,"arco-typography")][contains(text(),"Content")]]',
                            ],
                            "Content type",
                        )
                        if not clicked:
                            clicked = await _click_button_by_text(["Content", "Content type"])
                        if clicked:
                            await self.delay(1)

                            try:
                                selected = False
                                selectors = [
                                    f'li[role="option"]:has-text("{content_type}")',
                                    f'xpath=//li[@role="option"][contains(., "{content_type}")]',
                                    f'.arco-select-option:has-text("{content_type}")',
                                ]
                                for selector in selectors:
                                    try:
                                        option = page.locator(selector).first
                                        if await option.count() > 0 and await option.is_visible():
                                            await option.click(force=True, timeout=3000)
                                            self.logger.info(
                                                "Selected content type", value=content_type
                                            )
                                            applied["creators"]["content_type"].append(
                                                content_type
                                            )
                                            selected = True
                                            break
                                    except Exception:
                                        continue
                                if not selected:
                                    self.logger.warning(
                                        "Content type option not found", value=content_type
                                    )
                            except Exception as exc:
                                self.logger.warning(
                                    "Content type selection failed",
                                    value=content_type,
                                    error=str(exc),
                                )
                        await self.click_blank_area(page)
            else:
                self.logger.info("Skip content type filter (empty)")

            await self.click_blank_area(page)

            if self.min_fans and self.min_fans > 0:
                self.logger.info("Step 3.1: minimum followers", min_fans=self.min_fans)
                await _open_followers_panel()
                follower_input_visible = False
                try:
                    follower_input_visible = await page.locator(
                        "#followerSize input"
                    ).first.is_visible()
                except Exception:
                    follower_input_visible = False

                if not follower_input_visible:
                    await click_first(
                        [
                            '#followerSize button',
                            '#followerCount button',
                            'button[data-tid="m4b_button"]:has(div:has-text("Follower count"))',
                            'button:has(div:has-text("Follower count"))',
                            'button:has-text("Follower count")',
                            'button:has(div:has-text("Follower size"))',
                            'div.arco-spin-children button:has-text("Follower count")',
                            'button[data-e2e="9ed553d9-3ba8-d083"]:has(div:has-text("Follower count"))',
                            'button[data-e2e="9ed553d9-3ba8-d083"]:has(div:has-text("Follower size"))',
                            'xpath=//button[.//div[contains(text(),"Follower count")]]',
                            'xpath=//button[.//div[contains(text(),"Follower size")]]',
                        ],
                        "Follower count",
                        allow_related=False,
                    )

                filled = await fill_first(
                    [
                        'input[data-e2e="d9c26458-94d3-e920"]',
                        '#followerSize input',
                        '#followerCount input',
                        '#followerSize input[data-tid="m4b_input"]',
                        'xpath=//*[@id="followerSize"]//input[1]',
                        'xpath=//*[@id="followerSize"]//span/div//div[1]/input[1]',
                        'xpath=//*[@id="followerSize"]//input[position()=1]',
                        'xpath=//div[@id="followerSize"]//input[@type="text"][1]',
                        'xpath=//*[@id="followerCount"]//input[1]',
                    ],
                    str(self.min_fans),
                    "Follower min",
                )

                if not filled:
                    try:
                        filled = await page.evaluate(
                            """(val) => {
                            const candidates = [
                                "#followerSize input",
                                "#followerCount input"
                            ];
                            for (const sel of candidates) {
                                const input = document.querySelector(sel);
                                if (input) {
                                    input.focus();
                                    input.value = val;
                                    input.dispatchEvent(new Event("input", { bubbles: true }));
                                    input.dispatchEvent(new Event("change", { bubbles: true }));
                                    return true;
                                }
                            }
                            const labels = Array.from(document.querySelectorAll("*"))
                                .filter((el) => {
                                    const text = (el.textContent || "").trim();
                                    return text.includes("Follower count") || text.includes("Follower size");
                                });
                            for (const label of labels) {
                                const root = label.closest("div");
                                if (!root) continue;
                                const input = root.querySelector("input");
                                if (input) {
                                    input.focus();
                                    input.value = val;
                                    input.dispatchEvent(new Event("input", { bubbles: true }));
                                    input.dispatchEvent(new Event("change", { bubbles: true }));
                                    return true;
                                }
                            }
                            return false;
                        }""",
                            str(self.min_fans),
                        )
                    except Exception:
                        filled = False

                if filled:
                    applied["followers"]["follower_min"] = self.min_fans
                else:
                    self.logger.warning("Follower count input not filled")
                await self.click_blank_area(page)
            else:
                self.logger.info("Skip follower count filter")

            if self.age_ranges:
                self.logger.info("Step 3.2: follower age", ages=self.age_ranges)
                await _open_followers_panel()
                await self.delay(1)
                if await open_dropdown(
                    [
                        'button[data-tid="m4b_button"]:has(div:has-text("Follower age"))',
                        'button:has(div:has-text("Follower age"))',
                        'button:has-text("Follower age")',
                        'button[data-e2e="9ed553d9-3ba8-d083"]:has(div:has-text("Follower age"))',
                        'xpath=//button[.//div[contains(text(),"Follower age")]]',
                        '#followerAge button',
                        'xpath=//*[@id="followerAge"]//button',
                    ],
                    "Follower age",
                ):
                    chosen = await select_options_in_visible_popup(self.age_ranges)
                    applied["followers"]["age"].extend(chosen)
                    await self.click_blank_area(page)
            else:
                self.logger.info("Skip follower age filter")

            await self.click_blank_area(page)

            if self.gender:
                self.logger.info(
                    "Step 3.3: follower gender",
                    gender=self.gender,
                    percentage=self.gender_percentage,
                )
                await _open_followers_panel()
                if await open_dropdown(
                    [
                        'button[data-tid="m4b_button"]:has(div:has-text("Follower gender"))',
                        'button:has(div:has-text("Follower gender"))',
                        'button:has-text("Follower gender")',
                        'button:has(div:has-text("Follower gend"))',
                        'button[data-e2e="9ed553d9-3ba8-d083"]:has(div:has-text("Follower gend"))',
                        'xpath=//button[.//div[contains(text(),"Follower gend")]]',
                    ],
                    "Follower gender",
                ):
                    await self.delay(1)
                    chosen = await select_options_in_visible_popup([self.gender])
                    if chosen:
                        applied["followers"]["gender"] = self.gender
                        try:
                            slider_button = page.locator(
                                '//div[@id="followerGender"]//div[@role="slider"]'
                            ).first
                            slider_track = page.locator(
                                '//div[@id="followerGender"]//div[contains(@class,"arco-slider-road")]'
                            ).first

                            button_box = await slider_button.bounding_box()
                            track_box = await slider_track.bounding_box()

                            if button_box and track_box:
                                start_x = track_box["x"]
                                center_y = track_box["y"] + (track_box["height"] / 2)
                                width = track_box["width"]
                                target_percentage = (self.gender_percentage or 0) / 100.0
                                target_x = start_x + width * target_percentage

                                await page.mouse.move(
                                    button_box["x"] + button_box["width"] / 2, center_y
                                )
                                await page.mouse.down()
                                await page.mouse.move(target_x, center_y, steps=10)
                                await page.mouse.up()

                                applied["followers"]["gender_percentage"] = self.gender_percentage
                                self.logger.info(
                                    "Slider adjusted", percentage=self.gender_percentage
                                )
                            else:
                                self.logger.warning("Slider bounding box not available")
                        except Exception as exc:
                            self.logger.warning("Slider adjustment failed", error=str(exc))
            else:
                self.logger.info("Skip follower gender filter")

            await self.click_blank_area(page)

            performance_panel_selectors = ["button:has-text(\"Performance\")"]

            if self.gmv_ranges:
                self.logger.info("Step 4.1: GMV", gmv=self.gmv_ranges)
                for opt in self.gmv_ranges:
                    success = False
                    for attempt in range(3):
                        await ensure_panel_active("Performance", performance_panel_selectors)
                        await self.delay(1)
                        if await open_dropdown(
                            [
                                "#gmv button",
                                'button:has(div:has-text("GMV"))',
                                'button:has(div.arco-typography:has-text("G"))',
                                'xpath=//button[.//div[contains(text(),"GMV")]]',
                            ],
                            "GMV",
                        ):
                            await self.delay(1)
                            chosen = await select_options_in_visible_popup([opt])
                            if chosen:
                                applied["performance"]["gmv"].extend(chosen)
                                success = True
                                break
                        else:
                            self.logger.warning("GMV dropdown not found", attempt=attempt + 1)
                            await self.click_blank_area(page)
                            await self.delay(1)
                    if not success:
                        self.logger.error("Failed to select GMV option", option=opt)
                    await self.click_blank_area(page)
            else:
                self.logger.info("Skip GMV filter")

            if self.sales_ranges:
                self.logger.info("Step 4.2: items sold", sales=self.sales_ranges)
                for opt in self.sales_ranges:
                    success = False
                    for attempt in range(3):
                        await ensure_panel_active("Performance", performance_panel_selectors)
                        await self.delay(1)
                        if await open_dropdown(
                            [
                                "#unitsSold button",
                                'button:has(div:has-text("Items so"))',
                                'button:has(div:has-text("Items sold"))',
                                'button:has(div.arco-typography:has-text("Items so"))',
                                'xpath=//button[.//div[contains(text(),"Items so")]]',
                                "#unitsSold button",
                                'button[data-e2e="9ed553d9-3ba8-d083"]',
                            ],
                            "Items sold",
                        ):
                            await self.delay(1)
                            chosen = await select_options_in_visible_popup([opt])
                            if chosen:
                                applied["performance"]["items_sold"].extend(chosen)
                                success = True
                                break
                        else:
                            self.logger.warning("Items sold dropdown not found", attempt=attempt + 1)
                            await self.click_blank_area(page)
                            await self.delay(1)
                    if not success:
                        self.logger.error("Failed to select items sold option", option=opt)
                    await self.click_blank_area(page)
            else:
                self.logger.info("Skip items sold filter")

            if self.avg_views and self.avg_views > 0:
                self.logger.info("Step 4.3: average views", min_views=self.avg_views)
                await ensure_panel_active("Performance", performance_panel_selectors)
                await click_first(
                    [
                        'button:has(div:has-text("Average views per video"))',
                        'xpath=//button[.//div[contains(@class,"arco-typography")][normalize-space(text())="Average views per video"]]',
                        'xpath=(//*[@id="content-container"]//div[contains(@class,"index-module__button")]/button)[3]',
                    ],
                    "Average views",
                )
                if await fill_first(
                    [
                        'xpath=//*[@id="filter-container"]/div[2]/span/div/div[1]/input',
                        'input[data-tid="m4b_input"]:visible',
                        'input[type="text"]:visible',
                        'xpath=//div[@role="dialog"]//input[1]',
                    ],
                    str(self.avg_views),
                    "Average views min",
                ):
                    applied["performance"]["avg_views_min"] = self.avg_views
            else:
                self.logger.info("Skip average views filter")
            await self.click_blank_area(page)

            if self.min_engagement_rate and self.min_engagement_rate > 0:
                self.logger.info(
                    "Step 4.4: engagement rate", min_rate=self.min_engagement_rate
                )
                await ensure_panel_active("Performance", performance_panel_selectors)
                await click_first(
                    [
                        'button[data-e2e="9ed553d9-3ba8-d083"]',
                        'button:has(div:has-text("Engagement rate"))',
                        'xpath=//button[.//div[contains(@class,"arco-typography")][normalize-space(text())="Engagement rate"]]',
                        'xpath=(//*[@id="content-container"]//div[contains(@class,"index-module__button")]/button)[4]',
                    ],
                    "Engagement rate",
                )
                if await fill_first(
                    [
                        'xpath=//*[@id="filter-container"]/div[2]/span/div/div[1]/div/span/span/input',
                        'input[data-tid="m4b_input"]:visible',
                        'input[data-e2e="7f6a7b3f-260b-00c0"]',
                        'xpath=//div[@role="dialog"]//input[1]',
                        'input[type="text"]:visible',
                    ],
                    str(self.min_engagement_rate / 10),
                    "Engagement rate min",
                ):
                    applied["performance"]["engagement_min"] = self.min_engagement_rate
            else:
                self.logger.info("Skip engagement rate filter")
            await self.click_blank_area(page)

            self.logger.info("Filter summary before search", applied=applied)

            self.logger.info("Click search button")
            if not await click_first(
                [
                    'button:has(svg.arco-icon-search)',
                    'svg.arco-icon-search',
                    'button:has([class*="search"])',
                    'xpath=//button[.//svg[contains(@class,"search")]]',
                ],
                "Search button",
            ):
                self.logger.error("Search button not found")
                return False

            await wait_spinner_done()
            self.logger.info("Search and filter completed")
            return True
        except Exception as exc:
            self.logger.error("Search and filter failed", error=str(exc))
            return False

    async def get_creators_in_current_page(self, page) -> List[str]:
        creators = await page.evaluate(
            """
            () => {
                const creators = [];
                const nameElements = document.querySelectorAll('span[data-e2e="fbc99397-6043-1b37"]');
                nameElements.forEach(el => {
                    const text = el.textContent?.trim();
                    if (
                        text &&
                        text.length > 0 &&
                        !creators.includes(text) &&
                        !/^\\d+\\.?\\d*[KM]?$/.test(text)
                    ) {
                        creators.push(text);
                    }
                });
                return creators;
            }
            """
        )
        self.logger.info("Creators found in DOM", count=len(creators))
        return creators

    async def scroll_page_for_more(self, page) -> bool:
        self.logger.info("Scrolling for more creators")
        try:
            scrolled = await page.evaluate(
                """() => {
                const containers = [
                    document.querySelector('#content-container'),
                    document.querySelector('main'),
                    document.querySelector('[class*="scrollable"]'),
                    document.querySelector('[class*="scroll-container"]'),
                    document.querySelector('[style*="overflow: auto"]'),
                    document.querySelector('[style*="overflow-y: scroll"]'),
                    document.querySelector('[style*="overflow-y: auto"]')
                ];

                for (const container of containers) {
                    if (container && container.scrollHeight > container.clientHeight) {
                        const oldScrollTop = container.scrollTop;
                        container.scrollTo(0, container.scrollHeight);
                        if (container.scrollTop > oldScrollTop) {
                            return {
                                scrolled: true,
                                containerId: container.id || '',
                                containerClass: container.className || '',
                                scrollHeight: container.scrollHeight,
                                clientHeight: container.clientHeight,
                                scrollTop: container.scrollTop
                            };
                        }
                    }
                }

                const creatorCard = document.querySelector('[class*="creator-card"], [class*="item"]:has(span[data-e2e="fbc99397-6043-1b37"])');
                if (creatorCard) {
                    let parent = creatorCard.parentElement;
                    while (parent && parent !== document.body) {
                        if (parent.scrollHeight > parent.clientHeight) {
                            const oldScrollTop = parent.scrollTop;
                            parent.scrollTo(0, parent.scrollHeight);
                            if (parent.scrollTop > oldScrollTop) {
                                return {
                                    scrolled: true,
                                    containerId: parent.id || '',
                                    containerClass: parent.className || '',
                                    scrollHeight: parent.scrollHeight,
                                    clientHeight: parent.clientHeight,
                                    scrollTop: parent.scrollTop
                                };
                            }
                        }
                        parent = parent.parentElement;
                    }
                }

                window.scrollTo(0, document.body.scrollHeight);
                return {
                    scrolled: false,
                    message: 'No scrollable container found, used window.scrollTo',
                    bodyHeight: document.body.scrollHeight,
                    windowHeight: window.innerHeight
                };
            }"""
            )
            if isinstance(scrolled, dict) and scrolled.get("scrolled"):
                self.logger.info(
                    "Scrolled container",
                    container_id=scrolled.get("containerId") or None,
                    container_class=scrolled.get("containerClass") or None,
                    scroll_height=scrolled.get("scrollHeight"),
                    client_height=scrolled.get("clientHeight"),
                    scroll_top=scrolled.get("scrollTop"),
                )
            else:
                self.logger.warning(
                    "No scrollable container detected",
                    message=scrolled.get("message") if isinstance(scrolled, dict) else None,
                )
            await self.delay(1.5)
            return True
        except Exception as exc:
            self.logger.error("Scroll failed", error=str(exc))
            return False

    async def safe_extract_text(self, page, selector: str) -> str:
        try:
            if selector.startswith("//") or selector.startswith("(//"):
                locator = page.locator(f"xpath={selector}")
            else:
                locator = page.locator(selector)
            if await locator.count() > 0:
                text = await locator.first.text_content()
                return text.strip() if text else ""
        except PlaywrightTimeoutError:
            self.logger.warning("Timeout while waiting for selector", selector=selector)
        except Exception as exc:
            self.logger.warning("Error extracting text", selector=selector, error=str(exc))
        return ""

    async def click_creator(self, page, creator_name: str) -> Tuple[bool, Optional[str]]:
        row = page.locator(
            f'tr:has(span[data-e2e="fbc99397-6043-1b37"]:has-text("{creator_name}"))'
        ).first
        if await row.count() > 0:
            await row.scroll_into_view_if_needed()
            await row.wait_for(state="visible", timeout=5000)
            link = row.locator('a[href*="cid="], a[href*="/creator/detail"]').first
            if await link.count() > 0:
                href = await link.get_attribute("href")
                creator_id = self._parse_creator_id_from_url(href)
                await link.click()
                self.logger.info(
                    "Clicked creator link",
                    creator_name=creator_name,
                    creator_id=creator_id,
                )
                return True, creator_id
            await row.click()
            self.logger.info("Clicked creator row", creator_name=creator_name)
            return True, None

        for selector in [
            f'div[class*="creator-card"]:has(span:has-text("{creator_name}"))',
            f'div[class*="item"]:has(span:has-text("{creator_name}"))',
            f'a:has(span:has-text("{creator_name}"))',
            f'span:has-text("{creator_name}")',
        ]:
            element = page.locator(selector).first
            if await element.count() > 0:
                await element.scroll_into_view_if_needed()
                link = element.locator('a[href*="cid="], a[href*="/creator/detail"]').first
                if await link.count() > 0:
                    href = await link.get_attribute("href")
                    creator_id = self._parse_creator_id_from_url(href)
                    await link.click()
                    self.logger.info(
                        "Clicked creator link",
                        creator_name=creator_name,
                        creator_id=creator_id,
                    )
                    return True, creator_id
                await element.click()
                self.logger.info("Clicked creator card", creator_name=creator_name)
                return True, None

        self.logger.warning("Creator not clickable", creator_name=creator_name)
        return False, None

    async def _wait_for_new_page(self, context, base_pages, timeout_ms: int = 10000):
        start = asyncio.get_event_loop().time()
        interval = 0.1
        while (asyncio.get_event_loop().time() - start) * 1000 < timeout_ms:
            for ctx_page in context.pages:
                if ctx_page not in base_pages:
                    return ctx_page
            await asyncio.sleep(interval)
        return None

    async def _open_detail_and_get_page(self, page, creator_name: str):
        base_pages = list(page.context.pages)
        clicked, fallback_creator_id = await self.click_creator(page, creator_name)

        if not clicked:
            raise PlaywrightError(f"Failed to click creator {creator_name}")

        new_page = await self._wait_for_new_page(page.context, base_pages, timeout_ms=10000)
        if new_page:
            await new_page.wait_for_load_state("domcontentloaded", timeout=15000)
            try:
                await new_page.wait_for_url(re.compile(r".*cid=\\d+.*"), timeout=10000)
            except PlaywrightTimeoutError:
                try:
                    await new_page.wait_for_url(re.compile(r"/creator/detail"), timeout=5000)
                except PlaywrightTimeoutError:
                    pass
            try:
                for candidate in page.context.pages:
                    if candidate is new_page:
                        continue
                    url = candidate.url or ""
                    if "cid=" in url or "/creator/detail" in url:
                        new_page = candidate
                        break
            except Exception:
                pass
            return new_page, True, fallback_creator_id

        try:
            await page.wait_for_url(re.compile(r"/creator/detail"), timeout=15000)
        except PlaywrightTimeoutError:
            await page.wait_for_selector("text=Partnered brands", timeout=8000)
        return page, False, fallback_creator_id

    async def close_detail_drawer(self, page) -> None:
        try:
            await page.keyboard.press("Escape")
            await self.delay(1)
            await page.keyboard.press("Escape")
            await self.delay(2)
        except Exception as exc:
            self.logger.warning("Failed to close detail drawer", error=str(exc))

    async def navigate_to_chat_page(
        self, page, *, creator_id: str, partner_id: Optional[str]
    ) -> bool:
        if not creator_id:
            self.logger.error("Missing creator_id; cannot navigate to chat page")
            return False

        market_id = self._market_id()
        base_domain = self._partner_domain()
        chat_url = (
            f"https://{base_domain}/partner/im?"
            f"creator_id={creator_id}&market={market_id}&enter_from=find_creator_detail"
        )

        self.logger.info(
            "Navigate to chat page",
            creator_id=creator_id,
            partner_id=partner_id,
            chat_url=chat_url,
        )

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    self.logger.info("Retrying chat page in new tab", attempt=attempt)
                    try:
                        context = page.context
                        if context and hasattr(context, "new_page"):
                            new_page = await context.new_page()
                            try:
                                await page.close()
                            except Exception:
                                pass
                            page = new_page
                            await self.delay(1)
                        else:
                            try:
                                await page.goto("about:blank", wait_until="load", timeout=5000)
                                await self.delay(1)
                            except Exception:
                                pass
                    except Exception as exc:
                        self.logger.warning(
                            "Failed to open new page for chat retry",
                            error=str(exc),
                        )

                await page.goto(chat_url, wait_until="networkidle", timeout=60_000)
                await self.delay(2)

                current_url = page.url or ""
                if "login" in current_url.lower() or "signin" in current_url.lower():
                    self.logger.error("Chat page redirected to login", current_url=current_url)
                    return False

                max_wait_seconds = 60
                wait_interval = 2
                max_retry_count = max_wait_seconds // wait_interval
                retry_count = 0
                textarea_selectors = [
                    'textarea[placeholder="Send a message"]',
                    'textarea[placeholder*="Send a message"]',
                    'textarea.index-module__textarea--qYh62',
                    'textarea[data-e2e="798845f5-2eb9-0980"]',
                    'textarea[placeholder="发送消息"]',
                    'textarea[placeholder*="发送消息"]',
                    'textarea[placeholder*="message" i]',
                    "#im_sdk_chat_input textarea",
                    'div[data-e2e="cda68c25-5112-89c2"] textarea',
                    "textarea",
                ]

                while retry_count < max_retry_count:
                    try:
                        try:
                            frames = page.frames
                            if len(frames) > 1:
                                self.logger.debug(
                                    "Chat page frame count", frame_count=len(frames)
                                )
                                for frame in frames:
                                    try:
                                        if await frame.locator("textarea").count() > 0:
                                            self.logger.info("Found textarea in iframe")
                                            break
                                    except Exception:
                                        continue
                        except Exception:
                            pass

                        found_textarea = False
                        for selector in textarea_selectors:
                            try:
                                textarea = page.locator(selector).first
                                if await textarea.count() == 0:
                                    continue
                                placeholder = None
                                try:
                                    placeholder = await textarea.get_attribute("placeholder")
                                except Exception:
                                    pass

                                if selector == "textarea" and placeholder is None:
                                    continue

                                if (
                                    placeholder is None
                                    or placeholder == ""
                                    or "Send a message" in placeholder
                                    or "发送消息" in placeholder
                                    or "message" in placeholder.lower()
                                ):
                                    try:
                                        if await textarea.is_visible():
                                            self.logger.info(
                                                "Chat input found",
                                                selector=selector,
                                                placeholder=placeholder,
                                            )
                                            found_textarea = True
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                continue

                        if found_textarea:
                            self.logger.info("Chat page fully loaded")
                            await self.delay(1.5)
                            try:
                                final_check = page.locator("textarea").first
                                if await final_check.count() > 0:
                                    self.logger.info("Final chat input check ok")
                                    return True
                            except Exception:
                                self.logger.info(
                                    "Final chat input check failed; treating as success"
                                )
                                return True

                        retry_count += 1
                        if retry_count % 5 == 0:
                            self.logger.info(
                                "Waiting for chat input",
                                waited=retry_count * wait_interval,
                                max_wait=max_wait_seconds,
                            )
                            current_url = page.url or ""
                            if "partner/im" not in current_url:
                                self.logger.warning(
                                    "Left chat page while waiting",
                                    current_url=current_url,
                                )
                                break

                        await self.delay(wait_interval)
                    except Exception as exc:
                        retry_count += 1
                        if retry_count == 1:
                            self.logger.debug(
                                "Chat input check error", error=str(exc)
                            )
                        await self.delay(wait_interval)

                self.logger.warning(
                    "Chat page attempt timed out",
                    attempt=attempt,
                    waited=max_wait_seconds,
                )
                if attempt < max_attempts:
                    self.logger.info(
                        "Retrying chat page",
                        next_attempt=attempt + 1,
                    )
                    await self.delay(2)
                    continue

                current_url = page.url or ""
                if "partner/im" in current_url and creator_id in current_url:
                    self.logger.warning(
                        "Chat URL ok but input not found",
                        current_url=current_url,
                    )
                    return False
                self.logger.error("Chat URL invalid", current_url=current_url)
                return False
            except Exception as exc:
                self.logger.error(
                    "Chat page navigation failed",
                    attempt=attempt,
                    creator_id=creator_id,
                    error=str(exc),
                    exc_info=True,
                )
                if attempt < max_attempts:
                    await self.delay(3)
                    continue
                return False
        self.logger.error("Chat page navigation ended unexpectedly")
        return False

    async def check_connection_status(self, page) -> Tuple[bool, bool]:
        self.logger.info("Checking connection status in chat")
        try:
            await page.wait_for_load_state("networkidle")
            await self.delay(3)

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

    async def extract_contact_info(self, page) -> Tuple[str, str]:
        self.logger.info("Extracting contact info from chat page")
        whatsapp = ""
        email = ""
        start = asyncio.get_running_loop().time()
        max_seconds = 15

        contact_button_xpath = '//*[@id="arco-tabs-0-panel-0"]/div/div/div[1]/button'
        try:
            button = page.locator(f"xpath={contact_button_xpath}").first
            if await button.count() == 0:
                self.logger.info("Contact info button not found")
                return whatsapp, email
            await button.wait_for(state="visible", timeout=2000)
            await button.click()
            await self.delay(1)
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
                            await self.delay(0.5)
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
                await self.delay(0.3)
        except Exception:
            try:
                await page.keyboard.press("Escape")
                await self.delay(0.3)
            except Exception:
                pass

        return whatsapp, email

    async def extract_creator_details(self, page, creator_name: str) -> Optional[Dict[str, Any]]:
        self.logger.info("Extracting creator details", creator_name=creator_name)
        await self._dismiss_verify_bar(page)
        try:
            is_detail_page = await page.evaluate(
                """() => {\n                const url = window.location.href;\n                return url.includes('/creator/detail') ||\n                    document.querySelector('div.text-head-l') !== null;\n            }"""
            )
            if not is_detail_page:
                self.logger.warning("Detail page not detected", creator_name=creator_name)
                return None
        except Exception:
            self.logger.warning("Unable to verify detail page", creator_name=creator_name)
            return None

        max_wait = 30
        wait_count = 0
        key_elements = [
            ("title", 'div.text-head-l:has-text("Creator details")'),
            ("categories", '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[2]/div[1]/span[1]/span[2]/span/span'),
            ("followers", '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[2]/div[1]/span[2]/span[2]/span/span'),
            ("intro", '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[2]/div[3]/div/span'),
            ("sales", '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[1]'),
        ]
        loaded_elements = set()

        while wait_count < max_wait:
            for elem_name, selector in key_elements:
                if elem_name in loaded_elements:
                    continue
                try:
                    if selector.startswith("//") or selector.startswith("(//"):
                        element = page.locator(f"xpath={selector}")
                    else:
                        element = page.locator(selector)
                    if await element.count() > 0:
                        loaded_elements.add(elem_name)
                except Exception:
                    continue

            if len(loaded_elements) == len(key_elements):
                break

            wait_count += 1
            await self.delay(1)
            if wait_count % 5 == 0:
                missing = {name for name, _ in key_elements} - loaded_elements
                self.logger.info(
                    "Waiting detail elements",
                    seconds=wait_count,
                    loaded=len(loaded_elements),
                    missing=list(missing),
                )

        if wait_count >= max_wait:
            self.logger.warning(
                "Detail page load timeout",
                waited=wait_count,
                loaded=len(loaded_elements),
            )
            return None

        await self.delay(2)

        creator_data: Dict[str, Any] = {
            "platform": "tiktok",
            "region": self.region,
            "brand_name": self.brand_name,
            "search_keywords": self.search_keywords_raw,
            "creator_name": "",
            "categories": "",
            "followers": "",
            "intro": "",
            "sales_revenue": "",
            "sales_units_sold": "",
            "sales_gpm": "",
            "sales_revenue_per_buyer": "",
            "gmv_per_sales_channel": "",
            "gmv_by_product_category": "",
            "avg_commission_rate": "",
            "collab_products": "",
            "partnered_brands": "",
            "product_price": "",
            "video_gpm": "",
            "videos": "",
            "avg_video_views": "",
            "avg_video_engagement_rate": "",
            "avg_video_likes": "",
            "avg_video_comments": "",
            "avg_video_shares": "",
            "live_gpm": "",
            "live_streams": "",
            "avg_live_views": "",
            "avg_live_engagement_rate": "",
            "avg_live_likes": "",
            "avg_live_comments": "",
            "avg_live_shares": "",
            "followers_male": "",
            "followers_female": "",
            "followers_18_24": "",
            "followers_25_34": "",
            "followers_35_44": "",
            "followers_45_54": "",
            "followers_55_more": "",
            "creator_chaturl": "",
            "creator_id": "",
            "partner_id": "",
            "connect": False,
            "reply": False,
            "send": False,
            "send_time": "",
            "top_brands": "",
            "whatsapp": "",
            "email": "",
        }

        creator_data["creator_name"] = await self.safe_extract_text(
            page,
            '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[1]/div/span[1]/span[1]',
        )
        if not creator_data["creator_name"]:
            creator_data["creator_name"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[1]/div/span[1]/span',
            )

        current_url = page.url or ""
        self.logger.info("Detail page URL", url=current_url)
        partner_match = re.search(r"partner_id=(\\d+)", current_url)
        if partner_match:
            creator_data["partner_id"] = partner_match.group(1)
        cid_match = re.search(r"cid=(\\d+)", current_url)
        if cid_match:
            creator_data["creator_id"] = cid_match.group(1)
            creator_data["platform_creator_id"] = creator_data["creator_id"]
        if not creator_data.get("creator_id"):
            creator_id_match = re.search(r"creator_id=(\\d+)", current_url)
            if creator_id_match:
                creator_data["creator_id"] = creator_id_match.group(1)
                creator_data["platform_creator_id"] = creator_data["creator_id"]
        if not creator_data.get("creator_id"):
            creator_id_from_dom = await self._extract_creator_id_from_dom(page)
            if creator_id_from_dom:
                creator_data["creator_id"] = creator_id_from_dom
                creator_data["platform_creator_id"] = creator_id_from_dom
        if not creator_data.get("creator_id"):
            self.logger.warning("Creator id missing after detail parse", url=current_url)

        try:
            creator_data["categories"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[2]/div[1]/span[1]/span[2]/span/span',
            )
            creator_data["followers"] = await self.safe_extract_text(
                page,
                'span[data-e2e="9e8f2473-a87f-db74"] span[data-e2e="7aed0dd7-48ba-6932"]',
            )
            if not creator_data["followers"]:
                creator_data["followers"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[2]/div[1]/span[2]/span[2]/span/span',
                )
            creator_data["intro"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[2]/div[3]/div/span',
            )

            creator_data["sales_revenue"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[1]/div/div[1]/div[2]/span',
            )
            if not creator_data["sales_revenue"]:
                creator_data["sales_revenue"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[1]/div/div[1]/div[2]/span/span',
                )
            creator_data["sales_units_sold"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[1]/div/div[2]/div[2]/span/span',
            )
            creator_data["sales_gpm"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[1]/div/div[3]/div[2]/span',
            )
            if not creator_data["sales_gpm"]:
                creator_data["sales_gpm"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[1]/div/div[3]/div[2]/span/span',
                )
            creator_data["sales_revenue_per_buyer"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[1]/div/div[4]/div[2]/span',
            )
            if not creator_data["sales_revenue_per_buyer"]:
                creator_data["sales_revenue_per_buyer"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[1]/div/div[4]/div[2]/span/span',
                )

            gmv_channel_parts: List[str] = []
            for xpath in [
                '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[2]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div[2]/div/div/div/div/div',
                '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[2]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div[3]/div/div/div/div/div',
            ]:
                text = await self.safe_extract_text(page, xpath)
                if text:
                    gmv_channel_parts.append(text)
            creator_data["gmv_per_sales_channel"] = " | ".join(gmv_channel_parts)

            gmv_category_parts: List[str] = []
            for xpath in [
                '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[2]/div/div/div/div/div/div[2]/div/div[2]/div[2]/div[2]/div[1]/div/div/div/div',
                '//*[@id="submodule_layout_container_id"]/div[5]/div[3]/div/div[2]/div/div/div/div/div/div[2]/div/div[2]/div[2]/div[3]/div[1]/div/div/div/div',
            ]:
                text = await self.safe_extract_text(page, xpath)
                if text:
                    gmv_category_parts.append(text)
            creator_data["gmv_by_product_category"] = " | ".join(gmv_category_parts)

            creator_data["avg_commission_rate"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[7]/div[2]/div/div/div/div[1]/div[2]/span/span',
            )
            creator_data["collab_products"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[7]/div[2]/div/div/div/div[2]/div[2]/span/span',
            )
            creator_data["partnered_brands"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[7]/div[2]/div/div/div/div[3]/div[2]/span/span',
            )

            top_brands_list: List[str] = []
            try:
                partnered_brands_count = 0
                if creator_data["partnered_brands"]:
                    match = re.search(r"(\\d+)", creator_data["partnered_brands"])
                    if match:
                        partnered_brands_count = int(match.group(1))
                if partnered_brands_count > 0:
                    view_button = page.locator(
                        'xpath=//*[@id="submodule_layout_container_id"]/div[7]/div[2]/div/div/div/div[3]/div[2]/button'
                    ).first
                    if await view_button.count() > 0:
                        await view_button.click()
                        await self.delay(1.5)
                        for idx in range(2, partnered_brands_count + 2):
                            brand_xpath = (
                                "//*[@id=\"submodule_layout_container_id\"]/div[7]/div[2]/div/div/div/div[3]/div[2]"
                                f"/div/span/div[1]/div/div/div/div/div/div[{idx}]"
                            )
                            brand_text = await self.safe_extract_text(page, brand_xpath)
                            if brand_text and brand_text.strip():
                                top_brands_list.append(brand_text.strip())
            except Exception as exc:
                self.logger.warning("Failed to read top brands", error=str(exc))

            creator_data["top_brands"] = ", ".join(top_brands_list) if top_brands_list else ""
            creator_data["product_price"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[7]/div[2]/div/div/div/div[4]/div[2]/span/span',
            )

            creator_data["video_gpm"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[1]/div[1]/div[2]',
            )
            if not creator_data["video_gpm"]:
                creator_data["video_gpm"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[1]/div[1]/div[2]/span/div/div/div/span',
                )
            creator_data["videos"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[1]/div[2]/div[2]/span/span',
            )
            creator_data["avg_video_views"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[1]/div[3]/div[2]/span/span',
            )
            creator_data["avg_video_engagement_rate"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[1]/div[4]/div[2]/span/span',
            )

            try:
                for xpath in [
                    '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[2]',
                    '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[3]',
                    '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[3]',
                ]:
                    element = page.locator(f"xpath={xpath}")
                    if await element.count() > 0:
                        await element.first.click()
                        await self.delay(0.1)

                creator_data["avg_video_likes"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[2]/div[2]/div[2]/span/span',
                )
                creator_data["avg_video_comments"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[2]/div[3]/div[2]/span/span',
                )
                creator_data["avg_video_shares"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[9]/div[2]/div[2]/div[4]/div[2]/span/span',
                )
            except Exception as exc:
                self.logger.warning("Failed to read video detail", error=str(exc))

            creator_data["live_gpm"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[1]/div[1]/div[2]',
            )
            if not creator_data["live_gpm"]:
                creator_data["live_gpm"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[1]/div[1]/div[2]/span/div/div/div/span',
                )
            creator_data["live_streams"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[1]/div[2]/div[2]/span/span',
            )
            creator_data["avg_live_views"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[1]/div[3]/div[2]/span/span',
            )
            creator_data["avg_live_engagement_rate"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[1]/div[4]/div[2]/span/span',
            )

            try:
                for xpath in [
                    '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[2]',
                    '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[3]',
                    '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[3]',
                ]:
                    element = page.locator(f"xpath={xpath}")
                    if await element.count() > 0:
                        await element.first.click()
                        await self.delay(1)

                creator_data["avg_live_likes"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[2]/div[2]/div[2]/span/span',
                )
                creator_data["avg_live_comments"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[2]/div[3]/div[2]/span/span',
                )
                creator_data["avg_live_shares"] = await self.safe_extract_text(
                    page,
                    '//*[@id="submodule_layout_container_id"]/div[11]/div[2]/div/div/div[2]/div[4]/div[2]/span/span',
                )
            except Exception as exc:
                self.logger.warning("Failed to read live detail", error=str(exc))

            creator_data["followers_male"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[13]/div[2]/div/div/div/div/div[1]/div[1]/div/div[2]/div[2]/div[3]/div[1]/div/div/div/div',
            )
            creator_data["followers_female"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[13]/div[2]/div/div/div/div/div[1]/div[1]/div/div[2]/div[2]/div[3]/div[2]/div/div/div/div',
            )
            creator_data["followers_18_24"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[13]/div[2]/div/div/div/div/div[1]/div[2]/div/div[2]/div[2]/div[3]/div[1]/div/div/div/div',
            )
            creator_data["followers_25_34"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[13]/div[2]/div/div/div/div/div[1]/div[2]/div/div[2]/div[2]/div[3]/div[2]/div/div/div/div',
            )
            creator_data["followers_35_44"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[13]/div[2]/div/div/div/div/div[1]/div[2]/div/div[2]/div[2]/div[3]/div[3]/div/div/div/div',
            )
            creator_data["followers_45_54"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[13]/div[2]/div/div/div/div/div[1]/div[2]/div/div[2]/div[2]/div[3]/div[4]/div/div/div/div',
            )
            creator_data["followers_55_more"] = await self.safe_extract_text(
                page,
                '//*[@id="submodule_layout_container_id"]/div[13]/div[2]/div/div/div/div/div[1]/div[2]/div/div[2]/div[2]/div[3]/div[5]/div/div/div/div',
            )
        except Exception as exc:
            self.logger.error("Failed to extract creator details", error=str(exc))

        if creator_data.get("creator_name"):
            creator_data["platform_creator_display_name"] = creator_data["creator_name"]
        return creator_data

    async def process_single_creator(self, page, creator_name: str) -> Optional[Dict[str, Any]]:
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                fallback_creator_id = await self._extract_creator_id_from_list(
                    page, creator_name
                )
                detail_page, is_new_tab, click_creator_id = await self._open_detail_and_get_page(
                    page, creator_name
                )
                if click_creator_id and not fallback_creator_id:
                    fallback_creator_id = click_creator_id
                try:
                    creator_data = await self.extract_creator_details(
                        detail_page, creator_name
                    )
                    if self._detail_data_incomplete(creator_data):
                        self.logger.warning(
                            "Creator detail incomplete; retry after verify close",
                            creator_name=creator_name,
                        )
                        await self._dismiss_verify_bar(detail_page)
                        creator_data = await self.extract_creator_details(
                            detail_page, creator_name
                        )
                    if self._detail_data_incomplete(creator_data):
                        self.logger.warning(
                            "Creator detail incomplete; refreshing detail page",
                            creator_name=creator_name,
                        )
                        detail_page, is_new_tab, refresh_creator_id = (
                            await self._refresh_creator_detail(
                                page, detail_page, creator_name, is_new_tab
                            )
                        )
                        if refresh_creator_id and not fallback_creator_id:
                            fallback_creator_id = refresh_creator_id
                        creator_data = await self.extract_creator_details(
                            detail_page, creator_name
                        )

                    if creator_data is None:
                        if not fallback_creator_id:
                            self.logger.warning(
                                "Creator detail missing and no fallback id",
                                creator_name=creator_name,
                            )
                            continue
                        creator_data = {
                            "platform": "tiktok",
                            "region": self.region,
                            "brand_name": self.brand_name,
                            "search_keywords": self.search_keywords_raw,
                            "creator_name": creator_name,
                        }

                    if (
                        not creator_data.get("creator_id")
                        and not creator_data.get("platform_creator_id")
                        and fallback_creator_id
                    ):
                        creator_data["creator_id"] = fallback_creator_id
                        creator_data["platform_creator_id"] = fallback_creator_id
                        self.logger.info(
                            "Applied fallback creator_id",
                            creator_name=creator_name,
                            creator_id=fallback_creator_id,
                        )
                    creator_id = creator_data.get("creator_id") or creator_data.get(
                        "platform_creator_id"
                    )
                    if creator_id:
                        creator_data["creator_chaturl"] = self._build_chat_url(creator_id)
                    if self._detail_data_incomplete(creator_data):
                        creator_data["skip_creator_upsert"] = True
                        self.logger.warning(
                            "Creator detail still incomplete; skip creator upsert",
                            creator_name=creator_name,
                            creator_id=creator_id,
                        )
                    try:
                        await self._enqueue_outreach_chatbot_task(
                            creator_data=creator_data
                        )
                    except Exception as exc:
                        self.logger.warning(
                            "Failed to enqueue outreach chatbot task",
                            creator_name=creator_name,
                            error=str(exc),
                        )
                    return creator_data
                finally:
                    if is_new_tab:
                        await detail_page.close()
                    else:
                        await self.close_detail_drawer(page)
            except Exception as exc:
                self.logger.warning(
                    "Creator processing failed",
                    creator_name=creator_name,
                    attempt=attempt,
                    error=str(exc),
                )
            await self.delay(1)
        return None

    def _build_ingestion_options(self) -> Dict[str, Any]:
        options: Dict[str, Any] = {
            "task_id": self.task_id,
            "account_name": self.account_profile.name if self.account_profile else None,
            "region": self.region,
            "brand_name": self.brand_name,
            "search_strategy": self.search_strategy,
        }
        if self.task_metadata:
            options.update(self.task_metadata)
        return options

    async def _ingest_creator_data(self, creator_data: Dict[str, Any]) -> None:
        if not self.task_id:
            self.task_id = str(uuid.uuid4()).upper()
        await self.ingestion_client.submit(
            source=self.source,
            operator_id=self.db_actor_id or self.task_id,
            options=self._build_ingestion_options(),
            rows=[creator_data],
        )

    async def load_all_creators(
        self,
        page,
        max_creators_to_load: Optional[int] = None,
        max_scroll_attempts: Optional[int] = None,
    ) -> List[str]:
        target_load_count = max_creators_to_load or self.max_creators_to_load
        max_attempts = max_scroll_attempts or self.max_scroll_attempts

        all_loaded_creators: List[str] = []
        scroll_attempts = 0
        last_count = 0
        no_new_content_count = 0

        self.logger.info(
            "Start scrolling to load creators",
            target_load_count=target_load_count,
            max_scroll_attempts=max_attempts,
        )

        while len(all_loaded_creators) < target_load_count and scroll_attempts < max_attempts:
            if self._should_stop():
                self.logger.warning("Reached run end time while loading creators")
                break
            scroll_attempts += 1

            current_creators = await self.get_creators_in_current_page(page)
            new_creators = []
            for creator in current_creators:
                if creator not in all_loaded_creators:
                    new_creators.append(creator)
                    all_loaded_creators.append(creator)

            current_count = len(all_loaded_creators)
            self.logger.info(
                "Scroll pass",
                attempt=scroll_attempts,
                new_count=len(new_creators),
                total=current_count,
            )

            if current_count >= target_load_count:
                self.logger.info("Reached target load count", target=target_load_count)
                break

            if current_count == last_count:
                no_new_content_count += 1
                self.logger.info("No new creators", streak=no_new_content_count)
                if no_new_content_count >= 3:
                    self.logger.info("No new creators after multiple scrolls; stopping")
                    break
            else:
                no_new_content_count = 0
                last_count = current_count

            if not await self.scroll_page_for_more(page):
                self.logger.warning("Scrolling failed; stopping")
                break

            await self.delay(1)

        self.logger.info("Creator loading complete", total=len(all_loaded_creators))
        return all_loaded_creators

    def _merge_search_strategy(
        self, search_strategy: Optional[Dict[str, Any]], search_keyword: Optional[str]
    ) -> Dict[str, Any]:
        strategy = dict(self.default_search_strategy)
        if search_strategy:
            strategy.update(search_strategy)
        if search_keyword is not None:
            strategy["search_keywords"] = search_keyword
        return strategy

    async def run(
        self,
        *,
        search_strategy: Optional[Dict[str, Any]] = None,
        search_keyword: Optional[str] = None,
        region: Optional[str] = None,
        account_name: Optional[str] = None,
        max_creators_to_load: Optional[int] = None,
        task_id: Optional[str] = None,
        brand_name: Optional[str] = None,
        task_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        async with self._run_lock:
            processed: List[str] = []
            result_status = "completed"
            error_message: Optional[str] = None
            self.task_metadata = dict(task_metadata or {})
            self.task_id = (
                str(task_id).strip().upper()
                if task_id
                else str(uuid.uuid4()).upper()
            )
            self.stop_reason = None
            self.task_started_at = None
            self.plan_execute_time = self._derive_run_at_time()
            self.run_deadline = self._derive_run_deadline()
            if self.plan_execute_time and "run_at_time" not in self.task_metadata:
                self.task_metadata["run_at_time"] = self.plan_execute_time.isoformat()
            if max_creators_to_load is not None:
                self.task_metadata.setdefault("max_creators", max_creators_to_load)
            else:
                self.task_metadata.setdefault("max_creators", self.max_creators_to_load)
            if brand_name:
                self.brand_name = str(brand_name).strip()
            else:
                meta_brand = self.task_metadata.get("brand_name")
                if not meta_brand and isinstance(self.task_metadata.get("brand"), dict):
                    meta_brand = self.task_metadata.get("brand", {}).get("name")
                self.brand_name = (str(meta_brand).strip() if meta_brand else "") or self.brand_name

            self._load_message_templates()

            if self.plan_execute_time and self.plan_execute_time > datetime.now():
                await self._sync_outreach_task(
                    status="pending",
                    message="waiting_for_run_at_time",
                )
                await self._await_run_at_time()

            self.task_started_at = datetime.utcnow()
            await self._start_outreach_control()

            try:
                effective_region = region
                if not effective_region and isinstance(self.task_metadata, dict):
                    effective_region = self.task_metadata.get("region") or None
                profile = self.resolve_profile(effective_region, account_name)
                await self.initialize(profile)
                if not self._page:
                    raise PlaywrightError("Playwright page not initialized")
                if effective_region:
                    normalized = str(effective_region).strip().upper()
                    if normalized and normalized != self.region:
                        self.region = normalized
                        self.target_url = self._build_creator_url()

                if not await self.login(self._page):
                    raise PlaywrightError("Login failed")

                if not await self.navigate_to_creator_connection(self._page):
                    raise PlaywrightError("Failed to reach creator page")

                effective_strategy = search_strategy
                if not effective_strategy and isinstance(self.task_metadata, dict):
                    effective_strategy = self.task_metadata.get("search_strategy")
                if effective_strategy and "search_strategy" not in self.task_metadata:
                    self.task_metadata["search_strategy"] = effective_strategy
                self.search_strategy = self._merge_search_strategy(
                    effective_strategy, search_keyword
                )
                self.parse_search_strategy()

                await self._sync_outreach_task(
                    status="running",
                    started_at=self.task_started_at,
                )

                if not await self.search_and_filter(self._page):
                    raise PlaywrightError("Search and filter failed")

                try:
                    await self._page.locator("body").click(
                        position={"x": 10, "y": 10}, force=True
                    )
                except Exception:
                    pass
                await self.delay(1)

                creators = await self.load_all_creators(
                    self._page, max_creators_to_load=max_creators_to_load
                )
                for idx, creator_name in enumerate(creators, start=1):
                    if self._should_stop():
                        result_status = "timeout"
                        break
                    creator_data = await self.process_single_creator(
                        self._page, creator_name
                    )
                    if not creator_data:
                        self.logger.warning(
                            "Creator extraction failed", creator_name=creator_name
                        )
                        continue
                    try:
                        await self._ingest_creator_data(creator_data)
                        processed.append(creator_name)
                        self.logger.info(
                            "Creator ingested",
                            creator_name=creator_name,
                            index=idx,
                            total=len(creators),
                        )
                    except Exception as exc:
                        self.logger.error(
                            "Creator ingestion failed",
                            creator_name=creator_name,
                            error=str(exc),
                            exc_info=True,
                        )
                if result_status != "timeout" and self.stop_reason:
                    result_status = "timeout"
                return processed
            except Exception as exc:
                result_status = "failed"
                error_message = str(exc)
                raise
            finally:
                self.task_finished_at = datetime.utcnow()
                run_seconds = None
                if self.task_started_at:
                    run_seconds = (self.task_finished_at - self.task_started_at).total_seconds()
                await self._sync_outreach_task(
                    status=result_status,
                    message=error_message or self.stop_reason,
                    started_at=self.task_started_at,
                    finished_at=self.task_finished_at,
                    run_time_seconds=run_seconds,
                )
                await self._stop_outreach_control()

    async def run_from_payload(self, body: Dict[str, Any]) -> List[str]:
        if not isinstance(body, dict):
            raise PlaywrightError("Invalid payload format")
        task_meta = body.get("task_metadata") or body.get("metadata") or {}
        if isinstance(task_meta, dict):
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
                "product_list",
                "productList",
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
                if key in body and key not in task_meta:
                    task_meta[key] = body.get(key)
        brand_name = body.get("brand_name")
        if not brand_name and isinstance(body.get("brand"), dict):
            brand_name = body.get("brand", {}).get("name")
        return await self.run(
            search_strategy=body.get("search_strategy"),
            search_keyword=body.get("search_keyword") or body.get("keyword"),
            region=body.get("region"),
            account_name=body.get("account_name"),
            max_creators_to_load=body.get("max_creators_to_load"),
            task_id=body.get("task_id") or body.get("taskId"),
            brand_name=brand_name,
            task_metadata=task_meta if isinstance(task_meta, dict) else {},
        )

    async def _start_outreach_control(self) -> None:
        if not self.task_id or self._outreach_control_started:
            return
        try:
            await self.outreach_control_client.submit(
                action="start",
                task_id=self.task_id,
            )
            self._outreach_control_started = True
        except Exception as exc:
            self.logger.warning(
                "Failed to start outreach control",
                task_id=self.task_id,
                error=str(exc),
            )

    async def _stop_outreach_control(self) -> None:
        if not self.task_id or not self._outreach_control_started:
            return
        try:
            await self.outreach_control_client.submit(
                action="end",
                task_id=self.task_id,
            )
            self._outreach_control_started = False
        except Exception as exc:
            self.logger.warning(
                "Failed to stop outreach control",
                task_id=self.task_id,
                error=str(exc),
            )
