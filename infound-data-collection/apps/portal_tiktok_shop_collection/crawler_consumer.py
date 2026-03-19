import asyncio
from typing import Any, Dict

from common.core.config import get_settings
from common.core.logger import get_logger

from .services.shop_collection_service import ShopCollectionService


class CrawlerConsumer:
    """Local bootstrap consumer for seller/shop collection sessions."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = get_logger().bind(consumer="portal_tiktok_shop_collection")
        self._stop_event = asyncio.Event()
        self._service: ShopCollectionService | None = None

    async def start(self) -> None:
        payload = self._build_bootstrap_payload()
        try:
            self.logger.info(
                "Starting shop collection bootstrap",
                account_name=payload.get("accountName"),
                region=payload.get("region"),
                shop_type=payload.get("shopType"),
            )
            self._service = ShopCollectionService()
            await self._service.run_from_payload(payload)
            self.logger.info(
                "Shop collection session is ready",
                current_url=self._service.current_url,
            )
        except Exception as exc:
            self.logger.error(
                "Shop collection bootstrap failed",
                error=str(exc),
                exc_info=True,
            )
            raise
        await self._stop_event.wait()

    async def stop(self) -> None:
        self._stop_event.set()
        if self._service:
            await self._service.close()
            self._service = None

    def _build_bootstrap_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "accountName": getattr(
                self.settings,
                "SHOP_COLLECTION_BOOTSTRAP_ACCOUNT_NAME",
                "",
            ),
            "region": getattr(self.settings, "SHOP_COLLECTION_BOOTSTRAP_REGION", ""),
            "shopType": getattr(self.settings, "SHOP_COLLECTION_BOOTSTRAP_SHOP_TYPE", ""),
            "entryUrl": getattr(self.settings, "SHOP_COLLECTION_BOOTSTRAP_ENTRY_URL", ""),
            "homeUrl": getattr(self.settings, "SHOP_COLLECTION_BOOTSTRAP_HOME_URL", ""),
            "waitForManualLogin": bool(
                getattr(self.settings, "SHOP_COLLECTION_MANUAL_LOGIN", True)
            ),
            "manualLoginTimeoutSeconds": int(
                getattr(
                    self.settings,
                    "SHOP_COLLECTION_MANUAL_LOGIN_TIMEOUT_SECONDS",
                    900,
                )
                or 900
            ),
            "captureOutreachFilters": bool(
                getattr(
                    self.settings,
                    "SHOP_COLLECTION_CAPTURE_OUTREACH_FILTERS",
                    True,
                )
            ),
            "captureRegion": getattr(
                self.settings,
                "SHOP_COLLECTION_CAPTURE_REGION",
                "MX",
            ),
            "captureTimeoutSeconds": int(
                getattr(
                    self.settings,
                    "SHOP_COLLECTION_CAPTURE_TIMEOUT_SECONDS",
                    60,
                )
                or 60
            ),
            "captureOutputDir": getattr(
                self.settings,
                "SHOP_COLLECTION_CAPTURE_OUTPUT_DIR",
                "",
            ),
        }
        return {key: value for key, value in payload.items() if value not in ("", None)}
