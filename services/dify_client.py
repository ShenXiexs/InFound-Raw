from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
import os
from typing import Dict, List, Optional

import requests


logger = logging.getLogger(__name__)


class DifyError(Exception):
    """Raised when Dify API returns an unexpected response."""


def _default_session(api_key: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {api_key}"})
    return session


_DEFAULT_API_BASE = (
    os.getenv("DIFY_BASE")
    or os.getenv("DIFY_API_BASE")
    or "https://api.dify.ai"
)
_DEFAULT_API_KEY = (
    os.getenv("DIFY_API_KEY")
    or os.getenv("DIFY_API_KEY_1104")
    or "app-mDDa4ZWe5VOe6TvPQvfpDFCI"
)
_DEFAULT_WORKFLOW_USER = (
    os.getenv("DIFY_WORKFLOW_USER")
    or os.getenv("DIFY_USER_ID")
    or "a1d9906b-6db-6-431d-bd1f-8f5e3d53b8a1"
)


@dataclass
class DifyConfig:
    api_base: str = _DEFAULT_API_BASE
    api_key: str = _DEFAULT_API_KEY
    request_timeout: int = 180  # seconds
    workflow_user: str = _DEFAULT_WORKFLOW_USER


class DifyClient:
    """Minimal client for invoking Dify workflow #1104."""

    FILE_UPLOAD_PATH = "/v1/files/upload"
    WORKFLOW_RUN_PATH = "/v1/workflows/run"

    def __init__(self, config: Optional[DifyConfig] = None, session: Optional[requests.Session] = None) -> None:
        self.config = config or DifyConfig()
        base = (self.config.api_base or "").rstrip("/")
        if base.lower().endswith("/v1"):
            base = base[:-3].rstrip("/")
        self.api_base = base or "https://api.dify.ai"
        self.session = session or _default_session(self.config.api_key)
        self._file_cache: Dict[str, str] = {}  # thumbnail url -> upload_file_id

    def close(self) -> None:
        self.session.close()

    # --------------------------------------------------------------------- #
    # Helpers for thumbnail conversion
    # --------------------------------------------------------------------- #
    @staticmethod
    def _parse_thumbnail_urls(raw: str) -> List[str]:
        if not raw:
            return []
        parts = [p.strip() for p in re.split(r"[,\n;]+", raw) if p.strip()]
        # Keep original order, remove duplicates while preserving order.
        seen = set()
        unique: List[str] = []
        for url in parts:
            if url and url not in seen:
                unique.append(url)
                seen.add(url)
        return unique

    def _download_binary(self, url: str, timeout: float = 20.0) -> Optional[requests.Response]:
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to download thumbnail %s: %s", url, exc)
            return None

    def _upload_file(self, name: str, content: bytes, mime_type: str) -> Optional[str]:
        upload_url = f"{self.api_base}{self.FILE_UPLOAD_PATH}"
        files = {"file": (name, content, mime_type or "application/octet-stream")}
        data = {}
        if self.config.workflow_user:
            data["user"] = self.config.workflow_user
        try:
            resp = self.session.post(
                upload_url,
                files=files,
                data=data or None,
                timeout=self.config.request_timeout,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Upload to Dify failed: %s", exc)
            return None
        data = resp.json()
        return data.get("id")

    def build_thumbnail_payload(self, raw_value: str, limit: int = 1) -> List[Dict[str, str]]:
        """Turn raw thumbnail field into Dify file references."""
        urls = self._parse_thumbnail_urls(raw_value)
        if not urls:
            return []

        file_refs: List[Dict[str, str]] = []
        for url in urls[:limit]:
            if url in self._file_cache:
                upload_file_id = self._file_cache[url]
            else:
                response = self._download_binary(url)
                if not response:
                    continue
                upload_file_id = self._upload_file(
                    "thumbnail",
                    response.content,
                    response.headers.get("Content-Type", ""),
                )
                if not upload_file_id:
                    continue
                self._file_cache[url] = upload_file_id

            file_refs.append(
                {
                    "type": "image",
                    "transfer_method": "local_file",
                    "upload_file_id": upload_file_id,
                }
            )
        return file_refs

    # --------------------------------------------------------------------- #
    # Workflow invocation
    # --------------------------------------------------------------------- #
    def run_workflow(self, inputs: Dict[str, object], response_mode: str = "streaming") -> Dict[str, object]:
        url = f"{self.api_base}{self.WORKFLOW_RUN_PATH}"
        payload = {
            "inputs": inputs,
            "response_mode": response_mode,
            "user": inputs.get("sys_user_id") or self.config.workflow_user,
        }

        # Keep json headers separate to avoid mutating session headers.
        headers = {"Content-Type": "application/json"}

        if response_mode == "streaming":
            return self._run_streaming(url, payload, headers)

        try:
            resp = self.session.post(url, headers=headers, json=payload, timeout=self.config.request_timeout)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise DifyError(f"Dify workflow call failed: {exc}") from exc
        try:
            return resp.json().get("data", {}).get("outputs", {})
        except Exception as exc:  # noqa: BLE001
            raise DifyError(f"Invalid JSON from Dify: {exc}") from exc

    def _run_streaming(self, url: str, payload: Dict[str, object], headers: Dict[str, str]) -> Dict[str, object]:
        try:
            resp = self.session.post(
                url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=self.config.request_timeout,
            )
        except Exception as exc:  # noqa: BLE001
            raise DifyError(f"Failed to start Dify stream: {exc}") from exc

        if resp.status_code != 200:
            text = resp.text[:500]
            resp.close()
            raise DifyError(f"Dify returned HTTP {resp.status_code}: {text}")

        outputs: Optional[Dict[str, object]] = None
        start_time = time.time()

        for raw_line in resp.iter_lines(decode_unicode=True):
            if time.time() - start_time > self.config.request_timeout:
                resp.close()
                raise DifyError("Dify workflow stream timed out.")

            if not raw_line:
                continue
            if raw_line.startswith("event:"):
                continue
            if raw_line.startswith("data: "):
                raw_line = raw_line[6:]
            else:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "workflow_finished":
                outputs = event.get("data", {}).get("outputs")
                break

        resp.close()
        if outputs is None:
            raise DifyError("Failed to obtain workflow outputs from stream.")
        return outputs
def data_to_json(value: Optional[object]) -> str:
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)
