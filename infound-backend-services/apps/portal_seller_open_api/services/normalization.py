from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

SIGNED_BIGINT_MAX = 9_223_372_036_854_775_807
PREFERRED_UUID_NODE = 0x2AA7A70856D4


def generate_bigint_id() -> int:
    return (uuid.uuid4().int % (SIGNED_BIGINT_MAX - 1)) + 1


def generate_uppercase_uuid(seed: Any = None) -> str:
    if seed is not None:
        text = str(seed).strip()
        if text:
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, text)).upper()
    return str(uuid.uuid1(node=PREFERRED_UUID_NODE)).upper()


def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_identifier(value: Any) -> Optional[str]:
    return clean_text(value)


def normalize_region_code(value: Any) -> Optional[str]:
    text = clean_text(value)
    return text.upper() if text else None


def _parse_human_number(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    raw = str(value).strip()
    if not raw:
        return None

    cleaned = (
        raw.replace(",", "")
        .replace(" ", "")
        .replace("\u00a0", "")
        .replace("$", "")
        .replace("\u20ac", "")
        .replace("\u00a3", "")
        .replace("\u00a5", "")
    )
    cleaned = re.sub(r"(?i)\b(?:usd|mxn|eur|gbp|cny)\b", "", cleaned)
    cleaned = re.sub(r"(?i)\bp(\.\.\.|…)\s*", "", cleaned)

    match = re.search(r"(-?\d+(?:\.\d+)?)([kKmMbBtT]?)", cleaned)
    if not match:
        return None

    number = Decimal(match.group(1))
    suffix = (match.group(2) or "").lower()
    multiplier = {
        "": Decimal("1"),
        "k": Decimal("1000"),
        "m": Decimal("1000000"),
        "b": Decimal("1000000000"),
        "t": Decimal("1000000000000"),
    }.get(suffix)
    if multiplier is None:
        return None
    return number * multiplier


def normalize_int(value: Any) -> Optional[int]:
    try:
        number = _parse_human_number(value)
        if number is None:
            return None
        return int(number)
    except Exception:
        return None


def normalize_decimal(value: Any) -> Optional[Decimal]:
    try:
        number = _parse_human_number(value)
        if number is None:
            return None
        return Decimal(number)
    except Exception:
        return None


def normalize_ratio_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None

    raw_text = str(value).strip()
    parsed = normalize_decimal(value)
    if parsed is None:
        return None

    if "%" in raw_text:
        return parsed / Decimal("100")
    if abs(parsed) <= Decimal("1"):
        return parsed
    if abs(parsed) <= Decimal("100"):
        return parsed / Decimal("100")
    return parsed


def normalize_bool_flag(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, Decimal)):
        return 1 if int(value) != 0 else 0

    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y"}:
        return 1
    if text in {"0", "false", "no", "n"}:
        return 0
    return None


def normalize_outreach_status(value: Any) -> str:
    text = (clean_text(value) or "").lower()
    mapping = {
        "0": "0",
        "pending": "0",
        "not_started": "0",
        "not-started": "0",
        "1": "1",
        "running": "1",
        "in_progress": "1",
        "in-progress": "1",
        "processing": "1",
        "2": "2",
        "ended": "2",
        "finished": "2",
        "stopped": "2",
        "failed": "2",
        "cancelled": "2",
        "canceled": "2",
        "terminated": "2",
        "3": "3",
        "completed": "3",
        "complete": "3",
        "done": "3",
        "success": "3",
        "succeeded": "3",
    }
    return mapping.get(text, "3")


def normalize_utc_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time())
    else:
        text = clean_text(value)
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y%m%d_%H%M%S",
        ):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            try:
                dt = datetime.fromisoformat(normalized)
            except ValueError:
                return None

    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def normalize_utc_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return normalize_utc_datetime(value).date()
    if isinstance(value, date):
        return value
    dt = normalize_utc_datetime(value)
    return dt.date() if dt else None


def duration_seconds(started_at: Optional[datetime], finished_at: Optional[datetime]) -> Optional[int]:
    if started_at is None or finished_at is None:
        return None
    delta = int((finished_at - started_at).total_seconds())
    return max(delta, 0)
