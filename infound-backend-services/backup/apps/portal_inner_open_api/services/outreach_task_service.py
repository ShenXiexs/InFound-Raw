from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.logger import get_logger
from common.models.infound import OutreachTasks
from apps.portal_inner_open_api.models.outreach_task import (
    OutreachTaskIngestionRequest,
    OutreachTaskIngestionResult,
)

logger = get_logger()

PREFERRED_UUID_NODE = 0x2AA7A70856D4


def _generate_uuid(value: Optional[str] = None) -> str:
    if value:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, value)).upper()
    return str(uuid.uuid1(node=PREFERRED_UUID_NODE)).upper()


def _normalize_uuid_text(value: Any) -> str:
    if value is None:
        return _generate_uuid()
    if isinstance(value, uuid.UUID):
        return str(value).upper()
    text = str(value).strip()
    if not text:
        return _generate_uuid()
    try:
        return str(uuid.UUID(text)).upper()
    except Exception:
        return _generate_uuid(text)


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_human_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).strip()
    if not raw:
        return None

    cleaned = (
        raw.replace(",", "")
        .replace(" ", "")
        .replace("\u00A0", "")
        .replace("$", "")
        .replace("\u20ac", "")
        .replace("\u00a3", "")
        .replace("\u00a5", "")
    )

    import re

    match = re.search(r"(-?\d+(?:\.\d+)?)([kKmMbBtT]?)", cleaned)
    if not match:
        return None

    number = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    multiplier = {
        "": 1.0,
        "k": 1_000.0,
        "m": 1_000_000.0,
        "b": 1_000_000_000.0,
        "t": 1_000_000_000_000.0,
    }.get(suffix, 1.0)
    return number * multiplier


def _to_int(value: Any) -> Optional[int]:
    try:
        parsed = _parse_human_number(value)
        if parsed is None:
            return None
        return int(parsed)
    except Exception:
        return None


def _ensure_json_array(value: Any) -> Optional[list]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        items = [item.strip() for item in stripped.split(",") if item.strip()]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        items = [str(value).strip()] if str(value).strip() else []
    return items or None


def _ensure_range_json(raw_value: Any) -> Optional[dict]:
    if raw_value is None:
        return None
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip().startswith("{"):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    text = str(raw_value).strip()
    if not text:
        return None
    return {"raw": text}


def _json_gender(value: Any) -> Optional[dict]:
    text = _clean_text(value)
    if not text:
        return None
    return {"raw": text}


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y%m%d_%H%M%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_duration_to_seconds(value: Any) -> Optional[int]:
    if not value:
        return None
    text = str(value)
    hours = minutes = seconds = 0
    try:
        if "h" in text:
            hours = int(text.split("h")[0])
        if "min" in text:
            minutes = int(text.split("h")[-1].split("min")[0])
        if "s" in text:
            seconds = int(text.split("min")[-1].split("s")[0])
        total = hours * 3600 + minutes * 60 + seconds
        return total or None
    except Exception:
        return None


def _ensure_message_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return json.dumps(parsed, ensure_ascii=False)
    return json.dumps({"body": text}, ensure_ascii=False)


class OutreachTaskService:
    """Persist outreach task payload into MySQL."""

    def __init__(self) -> None:
        self.default_operator_id = "00000000-0000-0000-0000-000000000000"

    async def ingest(
        self, request: OutreachTaskIngestionRequest, session: AsyncSession
    ) -> OutreachTaskIngestionResult:
        row = request.task.model_dump()
        operator_id = request.operator_id or self.default_operator_id
        audit_id = _normalize_uuid_text(operator_id)
        utc_now = datetime.utcnow()

        payload = self._build_payload(row, audit_id, utc_now)
        task_id = payload["id"]

        await self._upsert_task(session, payload)

        logger.info(
            "Outreach task synced",
            source=request.source,
            task_id=task_id,
            status=payload.get("status"),
        )
        return OutreachTaskIngestionResult(task_id=task_id)

    def _build_payload(
        self, row_data: Dict[str, Any], audit_id: str, utc_now: datetime
    ) -> Dict[str, Any]:
        task_id = _clean_text(row_data.get("task_id")) or _generate_uuid()
        created_at = _parse_datetime(row_data.get("created_at")) or utc_now

        payload = {
            "id": task_id,
            "platform": _clean_text(row_data.get("platform")) or "tiktok",
            "task_name": _clean_text(row_data.get("task_name")) or "",
            "platform_campaign_id": _clean_text(
                row_data.get("platform_campaign_id") or row_data.get("campaign_id")
            ),
            "platform_campaign_name": _clean_text(
                row_data.get("platform_campaign_name") or row_data.get("campaign_name")
            ),
            "platform_product_id": _clean_text(
                row_data.get("platform_product_id") or row_data.get("product_id")
            ),
            "platform_product_name": _clean_text(
                row_data.get("platform_product_name") or row_data.get("product_name")
            ),
            "product_list": _ensure_json_array(
                row_data.get("product_list") or row_data.get("productList")
            ),
            "region": _clean_text(row_data.get("region")),
            "brand": _clean_text(row_data.get("brand")),
            "message_send_strategy": _to_int(
                row_data.get("only_first") or row_data.get("message_send_strategy")
            )
            or 0,
            "task_type": _clean_text(row_data.get("task_type")) or "Connect",
            "status": _clean_text(row_data.get("status")) or "pending",
            "message": _clean_text(row_data.get("message")),
            "accound_email": _clean_text(row_data.get("account_email")),
            "search_keywords": _clean_text(row_data.get("search_keywords")),
            "product_categories": _ensure_json_array(row_data.get("product_category")),
            "fans_age_range": _ensure_json_array(row_data.get("fans_age_range")),
            "fans_gender": _json_gender(row_data.get("fans_gender")),
            "content_types": _ensure_json_array(row_data.get("content_type")),
            "gmv_range": _ensure_range_json(row_data.get("gmv")),
            "sales_range": _ensure_range_json(row_data.get("sales")),
            "min_fans": _to_int(row_data.get("min_fans")),
            "min_avg_views": _to_int(row_data.get("avg_views") or row_data.get("min_avg_views")),
            "min_engagement_rate": _to_int(row_data.get("min_engagement_rate")),
            "first_message": _ensure_message_json(row_data.get("email_first_body")),
            "second_message": _ensure_message_json(row_data.get("email_later_body")),
            "new_creators_expect_count": _to_int(row_data.get("target_new_creators")),
            "max_creators": _to_int(row_data.get("max_creators")),
            "plan_execute_time": _parse_datetime(row_data.get("run_at_time")),
            "plan_stop_time": _parse_datetime(row_data.get("run_end_time")),
            "spend_time": _parse_duration_to_seconds(row_data.get("run_time")),
            "new_creators_real_count": _to_int(row_data.get("new_creators")),
            "real_start_at": _parse_datetime(row_data.get("started_at")),
            "real_end_at": _parse_datetime(row_data.get("finished_at")),
            "creator_id": audit_id,
            "creation_time": created_at,
            "last_modifier_id": audit_id,
            "last_modification_time": utc_now,
        }
        if payload.get("new_creators_real_count") is None:
            payload.pop("new_creators_real_count", None)
        return payload

    async def increment_progress(
        self,
        *,
        task_id: str,
        delta: int,
        operator_id: Optional[str],
        session: AsyncSession,
    ) -> int:
        task_id_clean = _clean_text(task_id)
        if not task_id_clean:
            raise ValueError("task_id is required")
        if delta <= 0:
            raise ValueError("delta must be positive")

        audit_id = _normalize_uuid_text(operator_id or self.default_operator_id)
        utc_now = datetime.utcnow()

        stmt = (
            update(OutreachTasks)
            .where(OutreachTasks.id == task_id_clean)
            .values(
                new_creators_real_count=(
                    func.coalesce(OutreachTasks.new_creators_real_count, 0) + delta
                ),
                last_modifier_id=audit_id,
                last_modification_time=utc_now,
            )
        )
        result = await session.execute(stmt)
        if not result.rowcount:
            raise ValueError("Outreach task not found")

        stmt = select(OutreachTasks.new_creators_real_count).where(
            OutreachTasks.id == task_id_clean
        )
        result = await session.execute(stmt)
        count = result.scalar_one_or_none()
        return int(count or 0)

    async def _upsert_task(
        self, session: AsyncSession, payload: Dict[str, Any]
    ) -> None:
        stmt = select(OutreachTasks).where(OutreachTasks.id == payload["id"])
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            for key, value in payload.items():
                if key == "id":
                    continue
                setattr(existing, key, value)
            return

        session.add(OutreachTasks(**payload))


outreach_task_service = OutreachTaskService()
