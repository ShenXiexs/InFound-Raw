from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from common.core.exceptions import MessageProcessingError, NonRetryableMessageError
from common.core.logger import get_logger

logger = get_logger()


class CreatorIngestionClient:
    """HTTP client used to push creator rows to the backend inner API."""

    def __init__(
        self,
        base_url: str,
        creator_path: str,
        header_name: str,
        token: str,
        timeout: float,
    ) -> None:
        if not token:
            raise RuntimeError("INNER_API token is required")
        self.url = urljoin(base_url.rstrip("/") + "/", creator_path.lstrip("/"))
        self.header_name = header_name
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def submit(
        self,
        *,
        source: str,
        operator_id: str,
        options: Dict[str, Any],
        rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not rows:
            raise MessageProcessingError("No rows to ingest")

        payload = {
            "source": source,
            "operatorId": operator_id,
            "options": _camelize_shallow(options or {}),
            "rows": [_camelize_shallow(row) for row in rows],
        }
        headers = {
            "Content-Type": "application/json",
            self.header_name: self.token,
        }

        client = await self._ensure_client()
        body = json.dumps(payload, default=self._json_default, ensure_ascii=False)
        try:
            response = await client.post(self.url, content=body.encode("utf-8"), headers=headers)
        except httpx.HTTPError as exc:
            logger.error("Inner API request failed", exc_info=True)
            raise MessageProcessingError(f"Failed to call inner API: {exc}") from exc

        if response.status_code >= 500:
            raise MessageProcessingError(
                f"Inner API returned {response.status_code}: {response.text}"
            )
        if response.status_code >= 400:
            raise NonRetryableMessageError(
                f"Inner API returned {response.status_code}: {response.text}"
            )

        try:
            result = response.json()
        except ValueError as exc:
            raise MessageProcessingError("Failed to decode inner API response") from exc

        if result.get("code") != 200:
            raise MessageProcessingError(f"Inner API error: {result.get('msg')}")

        logger.info(
            "Creator rows submitted",
            url=self.url,
            rows=len(rows),
            creators=result.get("data", {}).get("creators"),
        )
        return result.get("data") or {}

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _camelize_shallow(value: Dict[str, Any]) -> Dict[str, Any]:
    return {_to_camel(str(key)): item for key, item in value.items()}
