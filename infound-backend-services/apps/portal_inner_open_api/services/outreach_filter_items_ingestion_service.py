from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_inner_open_api.models.outreach_filter_items import (
    OutreachFilterItemsIngestionRequest,
    OutreachFilterItemsIngestionResult,
)
from core_base import get_logger
from shared_domain.models.infound import SellerTkShopPlatformSettings

DISPLAY_SCALAR_KEYS = {
    "module_title",
    "filter_title",
    "field_title",
    "label",
    "placeholder",
    "dismiss_text",
}
DISPLAY_LIST_KEYS = {"trigger_texts"}
DISPLAY_DICT_VALUE_KEYS = {"option_map"}
DEFAULT_OPERATOR_ID = "00000000-0000-0000-0000-000000000000"
REFERENCE_FILE_NAME = (
    "creator_filter_items_mx_mx_local_shop_20260330_000000_cn_en.json"
)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_region_code(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        raise ValueError("region_code is required")
    return text.upper()


def _normalize_shop_type(value: Any) -> str:
    text = (_clean_text(value) or "").upper().replace("-", "_").replace(" ", "_")
    if not text:
        raise ValueError("shop_type is required")
    aliases = {
        "LOCAL": "LOCAL",
        "LOCAL_SHOP": "LOCAL",
        "CROSS_BORDER": "CROSS_BORDER",
        "CROSSBORDER": "CROSS_BORDER",
        "CROSS_BORDER_SHOP": "CROSS_BORDER",
    }
    return aliases.get(text, text)


def _default_reference_path() -> Path:
    app_root = Path(__file__).resolve().parents[1]
    return app_root / "references" / REFERENCE_FILE_NAME


@lru_cache(maxsize=1)
def _load_reference_translation_map(reference_file: str) -> Dict[str, str]:
    reference_path = Path(reference_file)
    if not reference_path.exists():
        raise FileNotFoundError(
            f"creator_filter_items reference file not found: {reference_path}"
        )

    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    english_payload = payload.get("en")
    chinese_payload = payload.get("cn")
    if not isinstance(english_payload, dict) or not isinstance(chinese_payload, dict):
        raise ValueError(
            "creator_filter_items reference file must contain top-level 'cn' and 'en' objects"
        )

    mapping: Dict[str, str] = {}
    _collect_translation_pairs(english_payload, chinese_payload, mapping)
    return mapping


def _collect_translation_pairs(
        english_node: Any,
        chinese_node: Any,
        mapping: Dict[str, str],
) -> None:
    if isinstance(english_node, dict) and isinstance(chinese_node, dict):
        for key in english_node.keys() & chinese_node.keys():
            english_value = english_node.get(key)
            chinese_value = chinese_node.get(key)

            if (
                    key in DISPLAY_SCALAR_KEYS
                    and isinstance(english_value, str)
                    and isinstance(chinese_value, str)
            ):
                _maybe_record_translation(mapping, english_value, chinese_value)
                continue

            if key in DISPLAY_LIST_KEYS:
                _collect_list_string_pairs(mapping, english_value, chinese_value)
                continue

            if key in DISPLAY_DICT_VALUE_KEYS:
                _collect_dict_string_pairs(mapping, english_value, chinese_value)
                continue

            _collect_translation_pairs(english_value, chinese_value, mapping)
        return

    if isinstance(english_node, list) and isinstance(chinese_node, list):
        for english_item, chinese_item in zip(english_node, chinese_node):
            _collect_translation_pairs(english_item, chinese_item, mapping)


def _collect_list_string_pairs(
        mapping: Dict[str, str],
        english_value: Any,
        chinese_value: Any,
) -> None:
    if not isinstance(english_value, list) or not isinstance(chinese_value, list):
        return
    for english_item, chinese_item in zip(english_value, chinese_value):
        if isinstance(english_item, str) and isinstance(chinese_item, str):
            _maybe_record_translation(mapping, english_item, chinese_item)


def _collect_dict_string_pairs(
        mapping: Dict[str, str],
        english_value: Any,
        chinese_value: Any,
) -> None:
    if not isinstance(english_value, dict) or not isinstance(chinese_value, dict):
        return
    for option_key in english_value.keys() & chinese_value.keys():
        english_item = english_value.get(option_key)
        chinese_item = chinese_value.get(option_key)
        if isinstance(english_item, str) and isinstance(chinese_item, str):
            _maybe_record_translation(mapping, english_item, chinese_item)


def _maybe_record_translation(
        mapping: Dict[str, str],
        english_text: str,
        chinese_text: str,
) -> None:
    english_clean = _clean_text(english_text)
    chinese_clean = _clean_text(chinese_text)
    if not english_clean or not chinese_clean:
        return
    mapping.setdefault(english_clean, chinese_clean)


def _localize_payload(
        value: Any,
        *,
        translation_map: Dict[str, str],
        untranslated_terms: Set[str],
) -> Any:
    if isinstance(value, dict):
        localized: Dict[str, Any] = {}
        for key, item in value.items():
            if key in DISPLAY_SCALAR_KEYS and isinstance(item, str):
                localized[key] = _translate_text(
                    item,
                    translation_map=translation_map,
                    untranslated_terms=untranslated_terms,
                )
                continue
            if key in DISPLAY_LIST_KEYS and isinstance(item, list):
                localized[key] = [
                    _translate_text(
                        part,
                        translation_map=translation_map,
                        untranslated_terms=untranslated_terms,
                    )
                    if isinstance(part, str)
                    else part
                    for part in item
                ]
                continue
            if key in DISPLAY_DICT_VALUE_KEYS and isinstance(item, dict):
                localized[key] = {
                    option_key: (
                        _translate_text(
                            option_value,
                            translation_map=translation_map,
                            untranslated_terms=untranslated_terms,
                        )
                        if isinstance(option_value, str)
                        else option_value
                    )
                    for option_key, option_value in item.items()
                }
                continue
            localized[key] = _localize_payload(
                item,
                translation_map=translation_map,
                untranslated_terms=untranslated_terms,
            )
        return localized

    if isinstance(value, list):
        return [
            _localize_payload(
                item,
                translation_map=translation_map,
                untranslated_terms=untranslated_terms,
            )
            for item in value
        ]

    return value


def _translate_text(
        value: str,
        *,
        translation_map: Dict[str, str],
        untranslated_terms: Set[str],
) -> str:
    text = _clean_text(value)
    if not text:
        return value

    translated = translation_map.get(text)
    if translated is not None:
        return translated

    if _should_record_untranslated(text):
        untranslated_terms.add(text)
    return value


def _should_record_untranslated(text: str) -> bool:
    normalized = _clean_text(text)
    if not normalized:
        return False
    return bool(re.search(r"[A-Za-z]", normalized))


def _ensure_creator_filter_items_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("creator_filter_items_en must be an object")
    modules = payload.get("modules")
    if not isinstance(modules, list):
        raise ValueError("creator_filter_items_en.modules must be a list")
    return payload


class OutreachFilterItemsIngestionService:
    """Persist bilingual creator_filter_items into seller_tk_shop_platform_settings."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.logger = get_logger()
        self.db_session = db_session
        self.reference_file = str(_default_reference_path())

    async def ingest(
            self,
            payload: OutreachFilterItemsIngestionRequest,
    ) -> OutreachFilterItemsIngestionResult:
        region_code = _normalize_region_code(payload.region_code)
        shop_type = _normalize_shop_type(payload.shop_type)
        operator_id = _clean_text(payload.operator_id) or DEFAULT_OPERATOR_ID

        english_payload = copy.deepcopy(
            _ensure_creator_filter_items_payload(payload.creator_filter_items_en)
        )
        english_payload["region_code"] = region_code
        english_payload["shop_type"] = shop_type
        if payload.generated_at and not english_payload.get("generated_at"):
            english_payload["generated_at"] = payload.generated_at
        if payload.capture_source and not english_payload.get("capture_source"):
            english_payload["capture_source"] = payload.capture_source
        if payload.page_ready_text and not english_payload.get("page_ready_text"):
            english_payload["page_ready_text"] = payload.page_ready_text

        stmt = select(SellerTkShopPlatformSettings).where(
            SellerTkShopPlatformSettings.region_code == region_code,
            SellerTkShopPlatformSettings.shop_type == shop_type,
            SellerTkShopPlatformSettings.is_active == 1,
        )
        rows = list((await self.db_session.execute(stmt)).scalars().all())
        if not rows:
            raise ValueError(
                f"No active seller_tk_shop_platform_settings found for {region_code}/{shop_type}"
            )
        if len(rows) > 1:
            raise ValueError(
                f"Multiple active seller_tk_shop_platform_settings rows found for {region_code}/{shop_type}"
            )

        translation_map = _load_reference_translation_map(self.reference_file)
        untranslated_terms: Set[str] = set()
        localized_payload = _localize_payload(
            english_payload,
            translation_map=translation_map,
            untranslated_terms=untranslated_terms,
        )

        settings_row = rows[0]
        settings_row.creator_filter_items = {
            "cn": localized_payload,
            "en": english_payload,
        }
        settings_row.last_modifier_id = operator_id
        settings_row.last_modification_time = datetime.now(timezone.utc)
        await self.db_session.commit()

        untranslated_list = sorted(untranslated_terms)
        self.logger.info(
            "creator_filter_items ingested",
            shop_platform_settings_id=settings_row.id,
            region_code=region_code,
            shop_type=shop_type,
            untranslated_terms=len(untranslated_list),
        )

        return OutreachFilterItemsIngestionResult(
            shop_platform_settings_id=settings_row.id,
            region_code=region_code,
            shop_type=shop_type,
            stored_locale_keys=["cn", "en"],
            untranslated_terms=untranslated_list,
            reference_file=self.reference_file,
        )
