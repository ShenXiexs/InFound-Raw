from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = "2026-03-30"

STATIC_OPTION_CATALOG: Dict[str, List[str]] = {
    "avgCommissionRate": [
        "All",
        "Less than 20%",
        "Less than 15%",
        "Less than 10%",
        "Less than 5%",
    ],
    "contentType": ["All", "Video", "LIVE"],
    "creatorAgency": ["All", "Managed by Agency", "Independent creators"],
    "followerAgeSelections": ["18 - 24", "25 - 34", "35 - 44", "45 - 54", "55+"],
    "followerGender": ["All", "Female", "Male"],
    "estPostRate": ["All", "OK", "Good", "Better"],
}

STATIC_PRESET_CATALOG: Dict[str, List[str]] = {
    "followerCountRange": ["0", "10K", "100K", "1M", "10M+"],
    "averageViewsPerVideoMin": ["0", "100", "1K", "10K", "100K+"],
    "averageViewersPerLiveMin": ["0", "100", "1K", "10K", "100K+"],
    "engagementRateMinPercent": ["0", "1", "3", "5", "10+"],
}

COUNT_SUFFIX_PATTERN = re.compile(r"^(?P<label>.+?)\s*\((?P<count>\d+)\)\s*$")


def build_creator_filter_items_payload(snapshot_payload: Dict[str, Any]) -> Dict[str, Any]:
    source = _as_dict(snapshot_payload.get("source"))
    modules = [
        _build_module_payload(module_payload)
        for module_payload in _as_list(snapshot_payload.get("modules"))
    ]
    sort_binding = _build_sort_binding_payload(snapshot_payload.get("sort_binding"))
    result: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "modules": modules,
        "shop_type": snapshot_payload.get("shop_type"),
        "region_code": snapshot_payload.get("region"),
        "generated_at": snapshot_payload.get("generated_at"),
        "sort_binding": sort_binding,
        "dsl_reference": source.get("dsl_reference"),
        "capture_source": source.get("service_name"),
        "page_ready_text": source.get("page_ready_text"),
    }
    search_binding = snapshot_payload.get("search_binding")
    if isinstance(search_binding, dict):
        result["search_binding"] = search_binding
    return result


def derive_creator_filter_items_output_path(snapshot_path: Path) -> Path:
    stem = snapshot_path.stem
    if stem.startswith("outreach_filters_"):
        stem = stem.replace("outreach_filters_", "creator_filter_items_", 1)
    else:
        stem = f"{stem}_creator_filter_items"
    return snapshot_path.with_name(f"{stem}.json")


def export_creator_filter_items_snapshot(
    *,
    snapshot_path: Path,
    output_path: Optional[Path] = None,
) -> Path:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    creator_filter_items = build_creator_filter_items_payload(payload)
    final_output_path = output_path or derive_creator_filter_items_output_path(snapshot_path)
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output_path.write_text(
        json.dumps(creator_filter_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return final_output_path


def _build_module_payload(module_payload: Any) -> Dict[str, Any]:
    module = _as_dict(module_payload)
    return {
        "module_key": module.get("module_key"),
        "module_title": module.get("module_title"),
        "filters": [
            _build_filter_payload(filter_payload)
            for filter_payload in _as_list(module.get("filters"))
        ],
    }


def _build_filter_payload(filter_payload: Any) -> Dict[str, Any]:
    filter_dict = _as_dict(filter_payload)
    snapshot = _as_dict(filter_dict.get("snapshot"))
    filter_key = _text(
        filter_dict.get("filter_key")
        or _as_dict(filter_dict.get("dsl_binding")).get("filter_key")
    )
    filter_kind = _text(filter_dict.get("filter_kind"))
    filter_title = _text(
        filter_dict.get("filter_title")
        or _as_dict(filter_dict.get("dsl_binding")).get("filter_title")
    )

    option_items = _build_option_items(
        filter_key=filter_key,
        filter_kind=filter_kind,
        snapshot=snapshot,
    )
    preset_option_items = _build_preset_option_items(
        filter_key=filter_key,
        snapshot=snapshot,
    )
    input_items = _build_input_items(snapshot)
    toggle_option_items = _build_toggle_option_items(
        filter_kind=filter_kind,
        filter_title=filter_title,
        snapshot=snapshot,
    )

    result: Dict[str, Any] = {
        "status": filter_dict.get("status"),
        "filter_key": filter_key,
        "dsl_binding": _as_dict(filter_dict.get("dsl_binding")),
        "filter_kind": filter_kind,
        "filter_title": filter_title,
        "snapshot_summary": {
            "option_count": len(_as_list(snapshot.get("options"))),
            "input_count": len(_as_list(snapshot.get("inputs"))),
            "checkbox_count": len(_as_list(snapshot.get("checkbox_labels"))),
            "button_texts": _as_list(snapshot.get("button_texts")),
            "active_root_dom_path": snapshot.get("active_root_dom_path"),
        },
    }
    if option_items:
        result["option_items"] = option_items
    if filter_kind == "cascader_multiple" and option_items:
        result["option_tree"] = [
            {
                "label": item["label"],
                "value": item["value"],
                "raw_label": item.get("raw_label"),
                "count_hint": item.get("count_hint"),
                "children": [],
            }
            for item in option_items
        ]
    if preset_option_items:
        result["preset_option_items"] = preset_option_items
    if input_items:
        result["input_items"] = input_items
    if toggle_option_items:
        result["toggle_option_items"] = toggle_option_items
    if filter_kind == "checkbox":
        result["supported_values"] = [False, True]
        result["current_checked"] = bool(snapshot.get("checked"))
    return result


def _build_sort_binding_payload(sort_binding_payload: Any) -> Dict[str, Any]:
    sort_binding = _as_dict(sort_binding_payload)
    snapshot = _as_dict(sort_binding.get("snapshot"))
    dsl_binding = _as_dict(sort_binding.get("dsl_binding"))
    option_map = _as_dict(dsl_binding.get("option_map"))
    option_items: List[Dict[str, Any]] = []
    if option_map:
        for key in sorted(option_map.keys(), key=_sort_key):
            label = _text(option_map.get(key))
            if not label:
                continue
            option_items.append(
                {
                    "label": label,
                    "value": str(key),
                }
            )
    else:
        option_items = _build_option_items(
            filter_key=_text(sort_binding.get("field_key") or "filterSortBy"),
            filter_kind="single_select",
            snapshot=snapshot,
        )

    result: Dict[str, Any] = {
        "status": sort_binding.get("status"),
        "field_key": sort_binding.get("field_key"),
        "field_title": sort_binding.get("field_title"),
        "dsl_binding": dsl_binding,
    }
    if option_items:
        result["option_items"] = option_items
    result["snapshot_summary"] = {
        "option_count": len(_as_list(snapshot.get("options"))),
        "button_texts": _as_list(snapshot.get("button_texts")),
        "active_root_dom_path": snapshot.get("active_root_dom_path"),
    }
    return result


def _build_option_items(
    *,
    filter_key: str,
    filter_kind: str,
    snapshot: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if filter_kind not in {"single_select", "multi_select", "cascader_multiple"}:
        return []

    raw_items = [_build_option_item(option) for option in _as_list(snapshot.get("options"))]
    raw_items = [item for item in raw_items if item]
    known_labels = STATIC_OPTION_CATALOG.get(filter_key)

    if known_labels:
        raw_norms = {_norm(item["label"]) for item in raw_items}
        known_norms = {_norm(label) for label in known_labels}
        overlap = len(raw_norms & known_norms)
        overlap_ratio = overlap / max(len(known_norms), 1)
        if not raw_items or overlap_ratio < 0.5:
            raw_items = [_build_synthetic_option_item(label) for label in known_labels]
        else:
            existing = {_norm(item["label"]) for item in raw_items}
            for label in known_labels:
                if _norm(label) in existing:
                    continue
                raw_items.append(_build_synthetic_option_item(label))

    return _dedupe_option_items(raw_items)


def _build_preset_option_items(*, filter_key: str, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    values: List[str] = []
    for item in _as_list(snapshot.get("button_texts")):
        text = _text(item)
        if not text:
            continue
        values.append(text)

    if not values:
        values = list(STATIC_PRESET_CATALOG.get(filter_key, []))

    deduped: List[str] = []
    seen = set()
    for value in values:
        token = _norm(value)
        if not token or token in seen:
            continue
        seen.add(token)
        deduped.append(value)

    return [{"label": item, "value": item} for item in deduped]


def _build_input_items(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for index, input_item in enumerate(_as_list(snapshot.get("inputs")), start=1):
        input_payload = _as_dict(input_item)
        items.append(
            {
                "index": index,
                "value": _text(input_payload.get("value")),
                "placeholder": _text(input_payload.get("placeholder")),
                "input_type": _text(input_payload.get("input_type")),
                "dom_path": _text(input_payload.get("dom_path")),
            }
        )
    return items


def _build_toggle_option_items(
    *,
    filter_kind: str,
    filter_title: str,
    snapshot: Dict[str, Any],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if filter_kind == "checkbox":
        items.append({"label": "Unchecked", "value": False})
        items.append({"label": filter_title or "Checked", "value": True})
        return items

    seen = set()
    for item in _as_list(snapshot.get("checkbox_labels")):
        label = _text(_as_dict(item).get("label"))
        if not label:
            continue
        token = _norm(label)
        if token in seen:
            continue
        seen.add(token)
        items.append({"label": label, "value": True})
    return items


def _build_option_item(option_payload: Any) -> Optional[Dict[str, Any]]:
    option = _as_dict(option_payload)
    raw_label = _text(option.get("label"))
    if not raw_label and not _text(option.get("value")) and not _text(option.get("input_value")):
        return None

    label, count_hint = _split_label_and_count(raw_label)
    source_value = _text(option.get("value") or option.get("input_value"))
    value = source_value or label
    result: Dict[str, Any] = {
        "label": label,
        "value": value,
        "raw_label": raw_label,
        "selected_by_default": bool(option.get("input_checked")),
    }
    if source_value:
        result["source_value"] = source_value
    if count_hint is not None:
        result["count_hint"] = count_hint
    return result


def _build_synthetic_option_item(label: str) -> Dict[str, Any]:
    return {
        "label": label,
        "value": label,
        "raw_label": label,
        "selected_by_default": _norm(label) == "all",
    }


def _dedupe_option_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for item in items:
        key = (_norm(item.get("label")), _norm(item.get("value")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _split_label_and_count(raw_label: str) -> tuple[str, Optional[int]]:
    value = _text(raw_label)
    if not value:
        return "", None
    matched = COUNT_SUFFIX_PATTERN.match(value)
    if not matched:
        return value, None
    label = _text(matched.group("label"))
    count_raw = matched.group("count")
    try:
        count_hint = int(count_raw)
    except (TypeError, ValueError):
        count_hint = None
    return label, count_hint


def _sort_key(value: str) -> tuple[int, str]:
    token = _text(value)
    if token.isdigit():
        return (0, f"{int(token):08d}")
    return (1, token)


def _norm(value: Any) -> str:
    return _text(value).lower()


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []
