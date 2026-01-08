from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

from common.core.exceptions import MessageProcessingError, NonRetryableMessageError
from common.core.logger import get_logger

logger = get_logger()


class OutreachChatbotControlClient:
    """HTTP client used to publish outreach chatbot control messages via the inner API."""

    def __init__(
        self,
        base_url: str,
        control_path: str,
        header_name: str,
        token: str,
        timeout: float,
    ) -> None:
        if not token:
            raise RuntimeError("INNER_API token is required")
        self.url = urljoin(base_url.rstrip("/") + "/", control_path.lstrip("/"))
        self.header_name = header_name
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def submit(self, *, action: str, task_id: str) -> Dict[str, Any]:
        if not action or not task_id:
            raise MessageProcessingError("action/task_id required for outreach control")

        payload = {"action": action, "task_id": task_id}
        headers = {
            "Content-Type": "application/json",
            self.header_name: self.token,
        }

        client = await self._ensure_client()
        body = json.dumps(_camelize_shallow(payload), ensure_ascii=False)
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
            "Outreach chatbot control message published",
            url=self.url,
            action=action,
            task_id=task_id,
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


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _camelize_shallow(value: Dict[str, Any]) -> Dict[str, Any]:
    return {_to_camel(str(key)): item for key, item in value.items()}
