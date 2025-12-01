# database/ingest_product_excel.py
"""
将前端上传的 Excel 批量导入 product 表，并落一条 upload_batch 记录。
用法：
    ingest_product_excel(filepath, uploaded_by="alice", note="first upload")
    -> 返回 {batch_id, inserted, skipped}
"""

import logging
import time
import os
import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, List, Tuple, Union, Optional, Any, Callable
from pathlib import Path
from sqlalchemy import inspect, text, select

from database.db import get_session, now_beijing, engine
from database.models import UploadBatch, Product
from services.dify_client import DifyClient, DifyConfig, DifyError

logger = logging.getLogger(__name__)

# 映射：Excel列名 -> 表字段名（如果 Excel 就是同名字段，可以不改）
DEFAULT_COLUMN_MAP: Dict[str, str] = {
    "后端系统标识": "backend_system_id",
    "backend_system_id": "backend_system_id",
    "region": "region",
    "campaign_id": "campaign_id",
    "Campaign ID": "campaign_id",
    "活动 ID": "campaign_id",
    "campaign_name": "campaign_name",
    "Campaign name": "campaign_name",
    "活动名称": "campaign_name",
    "thumbnail": "thumbnail",
    "SKU_product": "SKU_product",
    "product_name": "product_name",
    "Product name": "product_name",
    "商品名称": "product_name",
    "product_id": "product_id",
    "Product ID": "product_id",
    "商品 ID": "product_id",
    "sale_price": "sale_price",
    "Sale price": "sale_price",
    "售价": "sale_price",
    "shop_name": "shop_name",
    "Shop name": "shop_name",
    "店铺名称": "shop_name",
    "campaign_start_time": "campaign_start_time",
    "Product effective start time": "campaign_start_time",
    "商品生效开始时间": "campaign_start_time",
    "campaign_end_time": "campaign_end_time",
    "Product effective end time": "campaign_end_time",
    "商品生效结束时间": "campaign_end_time",
    "creator_rate": "creator_rate",
    "Creator commission rate": "creator_rate",
    "创作者佣金率": "creator_rate",
    "partner_rate": "partner_rate",
    "Affiliate partner commission rate": "partner_rate",
    "联盟团长佣金率": "partner_rate",
    "cost_product": "cost_product",
    "available_samples": "available_samples",
    "stock": "stock",
    "item_sold": "item_sold",
    "affiliate_link": "affiliate_link",
    "product_link": "product_link",
    "Product link": "product_link",
    "商品链接": "product_link",
    "language": "language",
    "product_name_cn": "product_name_cn",
    "selling_point": "selling_point",
    "selling_point_cn": "selling_point_cn",
    "shooting_guide": "shooting_guide",
    "shooting_guide_cn": "shooting_guide_cn",
    "product_category_name": "product_category_name",
}

REQUIRED_FIELDS: List[str] = ["product_link"]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PRODUCT_DATA_DIR = DATA_DIR / "product_data"
PRODUCT_DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_PRODUCT_EXCEL = PRODUCT_DATA_DIR / "product_list.xlsx"

REGION_LANGUAGE_MAP: Dict[str, str] = {
    "US": "English",
    "GB": "English",
    "UK": "English",
    "CA": "English",
    "AU": "English",
    "NZ": "English",
    "PH": "English",
    "SG": "English",
    "MX": "Spanish",
    "ES": "Spanish",
    "AR": "Spanish",
    "CL": "Spanish",
    "CO": "Spanish",
    "PE": "Spanish",
    "BR": "Portuguese",
    "PT": "Portuguese",
    "FR": "French",
    "DE": "German",
    "IT": "Italian",
    "NL": "Dutch",
    "BE": "Dutch",
    "SE": "Swedish",
    "NO": "Norwegian",
    "DK": "Danish",
    "FI": "Finnish",
    "JP": "Japanese",
    "KR": "Korean",
    "TH": "Thai",
    "VN": "Vietnamese",
    "ID": "Indonesian",
    "MY": "Malay",
    "TR": "Turkish",
    "SA": "Arabic",
    "AE": "Arabic",
    "IN": "English",
}

DIFY_OUTPUT_COLUMNS = [
    "product_name_cn",
    "selling_point",
    "selling_point_cn",
    "shooting_guide",
    "shooting_guide_cn",
    "product_category_name",
]

_product_schema_checked = False
_upload_batch_schema_checked = False

def ensure_product_schema(force_refresh: bool = False) -> None:
    global _product_schema_checked
    if _product_schema_checked and not force_refresh:
        return

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("product")}
    alters: List[str] = []

    def add_column(name: str, ddl: str) -> None:
        if name not in columns:
            alters.append(ddl)

    add_column("backend_system_id", "ALTER TABLE product ADD COLUMN backend_system_id TEXT")
    add_column("campaign_id", "ALTER TABLE product ADD COLUMN campaign_id TEXT")
    add_column("product_name", "ALTER TABLE product ADD COLUMN product_name TEXT")
    add_column("product_id", "ALTER TABLE product ADD COLUMN product_id TEXT")
    add_column("sale_price", "ALTER TABLE product ADD COLUMN sale_price TEXT")
    add_column("campaign_start_time", "ALTER TABLE product ADD COLUMN campaign_start_time TEXT")
    add_column("campaign_end_time", "ALTER TABLE product ADD COLUMN campaign_end_time TEXT")
    add_column("creator_rate", "ALTER TABLE product ADD COLUMN creator_rate TEXT")
    add_column("cost_product", "ALTER TABLE product ADD COLUMN cost_product TEXT")
    add_column("stock", "ALTER TABLE product ADD COLUMN stock TEXT")
    add_column("item_sold", "ALTER TABLE product ADD COLUMN item_sold TEXT")
    add_column("product_name_cn", "ALTER TABLE product ADD COLUMN product_name_cn TEXT")
    add_column("selling_point", "ALTER TABLE product ADD COLUMN selling_point TEXT")
    add_column("selling_point_cn", "ALTER TABLE product ADD COLUMN selling_point_cn TEXT")
    add_column("shooting_guide", "ALTER TABLE product ADD COLUMN shooting_guide TEXT")
    add_column("shooting_guide_cn", "ALTER TABLE product ADD COLUMN shooting_guide_cn TEXT")
    add_column("product_category_name", "ALTER TABLE product ADD COLUMN product_category_name TEXT")
    add_column("SKU_product", "ALTER TABLE product ADD COLUMN SKU_product TEXT")
    add_column("campaign_name", "ALTER TABLE product ADD COLUMN campaign_name TEXT")
    add_column("thumbnail", "ALTER TABLE product ADD COLUMN thumbnail TEXT")
    add_column("partner_rate", "ALTER TABLE product ADD COLUMN partner_rate TEXT")
    add_column("available_samples", "ALTER TABLE product ADD COLUMN available_samples TEXT")
    add_column("affiliate_link", "ALTER TABLE product ADD COLUMN affiliate_link TEXT")
    add_column("product_link", "ALTER TABLE product ADD COLUMN product_link TEXT")
    add_column("shop_name", "ALTER TABLE product ADD COLUMN shop_name TEXT")
    add_column("source_row_index", "ALTER TABLE product ADD COLUMN source_row_index INTEGER")

    if alters:
        with engine.begin() as conn:
            for stmt in alters:
                conn.execute(text(stmt))

    _product_schema_checked = True


def ensure_upload_batch_schema(force_refresh: bool = False) -> None:
    global _upload_batch_schema_checked
    if _upload_batch_schema_checked and not force_refresh:
        return

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("upload_batch")}
    alters: List[str] = []

    def add_column(name: str, ddl: str) -> None:
        if name not in columns:
            alters.append(ddl)

    add_column("total_rows", "ALTER TABLE upload_batch ADD COLUMN total_rows INTEGER")
    add_column("dify_total", "ALTER TABLE upload_batch ADD COLUMN dify_total INTEGER")
    add_column("dify_processed", "ALTER TABLE upload_batch ADD COLUMN dify_processed INTEGER")
    add_column("dify_failed", "ALTER TABLE upload_batch ADD COLUMN dify_failed INTEGER")
    add_column("region_override", "ALTER TABLE upload_batch ADD COLUMN region_override VARCHAR(32)")

    if alters:
        with engine.begin() as conn:
            for stmt in alters:
                conn.execute(text(stmt))

    _upload_batch_schema_checked = True

def _read_excel(filepath: Union[str, Path]):
    """
    读取 Excel，返回 list[dict]；这里用 pandas，项目里已有依赖。
    """
    import pandas as pd
    df = pd.read_excel(filepath, dtype=str)  # 统一读成字符串，避免类型歧义
    rename_map = {src: dest for src, dest in DEFAULT_COLUMN_MAP.items() if src in df.columns}
    df = df.rename(columns=rename_map)
    all_columns = list(dict.fromkeys(DEFAULT_COLUMN_MAP.values()))
    cols = [c for c in all_columns if c in df.columns]
    if not cols:
        raise ValueError("Excel 中没有可识别的列，请检查列名是否与模板一致。")
    missing_required = [col for col in REQUIRED_FIELDS if col not in df.columns]
    if missing_required:
        raise ValueError(f"缺少必填列: {', '.join(missing_required)}")
    df = df[cols]
    # 空值统一为 ""，再转记录
    df = df.fillna("")
    return df


def _prepare_excel_records(
    filepath: Union[str, Path],
    override_region: Optional[str] = None,
):
    df = _read_excel(filepath)
    default_region = "MX"
    if override_region:
        override_region = override_region.strip()
    if override_region:
        df["region"] = override_region
    else:
        if "region" in df.columns:
            df["region"] = df["region"].apply(lambda x: (str(x).strip() if x is not None else ""))
            df.loc[df["region"] == "", "region"] = default_region
        else:
            df["region"] = default_region
    records = df.to_dict(orient="records")
    for idx, record in enumerate(records):
        record["_row_index"] = idx
    return records, df


def _region_to_language(region: str) -> str:
    if not region:
        return "English"
    region = region.strip().upper()
    return REGION_LANGUAGE_MAP.get(region, "English")


def _init_batch_progress(batch: UploadBatch, total_rows: int, dify_total: int, region_override: Optional[str]) -> None:
    batch.total_rows = total_rows
    batch.dify_total = dify_total
    batch.dify_processed = 0
    batch.dify_failed = 0
    batch.region_override = region_override or ""


def _update_batch_progress(batch_id: int, processed_inc: int = 0, failed_inc: int = 0, dify_total: Optional[int] = None) -> None:
    ensure_upload_batch_schema()
    with get_session() as db:
        batch = db.get(UploadBatch, batch_id)
        if not batch:
            return
        if dify_total is not None:
            batch.dify_total = dify_total
        if processed_inc:
            batch.dify_processed = (batch.dify_processed or 0) + processed_inc
        if failed_inc:
            batch.dify_failed = (batch.dify_failed or 0) + failed_inc
        db.commit()

def _calc_cost_from_sale_price(value: str) -> str:
    """
    提取价格中的数字，计算 30% 作为成本价，尽量保持与原值相同的前后缀符号。
    """
    if value is None:
        return ""
    text = str(value)
    if not text.strip():
        return ""
    normalized = text.replace(",", "")
    number_pattern = r"[-+]?\d+(?:\.\d+)?"
    matches = list(re.finditer(number_pattern, normalized))
    if not matches:
        return ""

    def _calc_str(num_text: str) -> str:
        try:
            price_val = Decimal(num_text)
        except InvalidOperation:
            return num_text
        cost_val = (price_val * Decimal("0.3")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{cost_val:.2f}"

    if len(matches) == 1:
        match = matches[0]
        prefix = normalized[: match.start()]
        suffix = normalized[match.end() :]
        return f"{prefix}{_calc_str(match.group())}{suffix}"

    result_parts: List[str] = []
    last_end = 0
    for match in matches:
        result_parts.append(normalized[last_end:match.start()])
        result_parts.append(_calc_str(match.group()))
        last_end = match.end()
    result_parts.append(normalized[last_end:])
    return "".join(result_parts)


def _count_dify_candidates(records: List[Dict[str, Any]]) -> int:
    return sum(1 for r in records if r.get("product_link") or r.get("product_id"))


def _build_dify_inputs(record: Dict[str, str], client: DifyClient) -> Dict[str, object]:
    thumbnail_value = record.get("thumbnail", "")
    thumbnails = client.build_thumbnail_payload(thumbnail_value, limit=1)
    inputs: Dict[str, object] = {
        "product_name": record.get("product_name", ""),
        "shop_name": record.get("shop_name", ""),
        "region": record.get("region", ""),
        "language": record.get("language") or _region_to_language(record.get("region", "")),
        "thumbnail": thumbnails,
        "product_link": record.get("product_link", ""),
    }
    # optional fields
    if record.get("campaign_name"):
        inputs["campaign_name"] = record["campaign_name"]
    if record.get("product_brief"):
        inputs["product_brief"] = record["product_brief"]
    if record.get("product_typing"):
        inputs["product_typing"] = record["product_typing"]
    return inputs


def _extract_dify_outputs(
    outputs: Dict[str, object],
    fallback_name: str,
    existing_product_name_cn: str,
) -> Dict[str, str]:
    market = outputs.get("market_strategy") or {}
    shooting = outputs.get("shooting_suggestion") or {}
    category = outputs.get("product_catogory_top3") or {}

def _stringify_values(value: object, sep: str = "\n") -> str:
    """
    将 Dify 传回的 list/dict/json 结构转成适合展示的字符串。
    - list[str] -> 每项一行，带序号
    - list[dict] -> 每个 dict 转成 "key: value" 形式，行间空一行
    - dict -> "key: value | key2: value2"
    - 其他 -> str()
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            if val in (None, "", [], {}):
                continue
            if isinstance(val, (list, dict)):
                rendered = _stringify_values(val)
            else:
                rendered = str(val).strip()
            if rendered:
                parts.append(f"{key}: {rendered}")
        return " | ".join(parts)

    if isinstance(value, list):
        rendered_items = []
        for idx, item in enumerate(value, 1):
            rendered = _stringify_values(item)
            if rendered:
                rendered_items.append(f"{idx}. {rendered}")
        return sep.join(rendered_items)

    return str(value).strip()


def _format_bullet_points(items: object, bullet: str = "• ") -> str:
    """把列表格式化为分点文本，适合前端展示。"""
    if isinstance(items, str):
        return items.strip()
    if not isinstance(items, list):
        return _stringify_values(items)

    lines: List[str] = []
    for entry in items:
        text = entry.strip() if isinstance(entry, str) else _stringify_values(entry)
        if text:
            lines.append(f"{bullet}{text}")
    return "\n".join(lines)


def _format_shots(shots: List[Dict[str, Any]], locale: str) -> str:
    if not shots:
        return ""
    colon = ":" if locale != "cn" else "："
    lines = []
    for shot in shots:
        scene = shot.get("scene") or shot.get("t") or ""
        line = shot.get("line") or ""
        parts = []
        if scene:
            parts.append(scene.strip())
        if line:
            parts.append(line.strip())
        if parts:
            lines.append(f"- {' '.join(parts)}")
    return "\n".join(lines)


def _format_hashtags(hashtags: object) -> str:
    if isinstance(hashtags, str):
        return hashtags.strip()
    if isinstance(hashtags, list):
        tags = [tag.strip() for tag in hashtags if isinstance(tag, str) and tag.strip()]
        return " ".join(tags)
    return ""


def _format_shooting_guides(items: object, locale: str = "default") -> str:
    """将拍摄指南 list[dict] 转为多段文本，仅取第一个示例。"""
    if isinstance(items, str):
        return items.strip()
    if not isinstance(items, list) or not items:
        return _stringify_values(items)

    guide = items[0] if isinstance(items[0], dict) else {}
    if not isinstance(guide, dict):
        return _stringify_values(guide)

    phrase_label = "🗣️ Frase inicial" if locale != "cn" else "🗣️ 开场句"
    script_label = "🎬 Guión sugerido" if locale != "cn" else "🎬 拍摄脚本"
    hashtag_label = "🏷️ Hashtags" if locale != "cn" else "🏷️ 话题标签"
    cta_label = "📣 CTA" if locale != "cn" else "📣 行动号召"

    title = guide.get("title", "").strip()
    style = guide.get("style", "").strip()
    header = title or style
    if title and style:
        header = f"{title} – {style}"

    block: List[str] = []
    if header:
        block.append(header)

    hook = guide.get("hook") or guide.get("opening") or ""
    if hook:
        block.append(f"{phrase_label}:\n{hook.strip()}")

    storyline = guide.get("storyline") or ""
    shots_text = _format_shots(guide.get("shots") or [], locale)
    script_parts: List[str] = []
    if storyline:
        script_parts.append(storyline.strip())
    if shots_text:
        script_parts.append(shots_text)
    if script_parts:
        block.append(f"{script_label}:\n" + "\n".join(script_parts))

    hashtags = _format_hashtags(guide.get("hashtags"))
    if hashtags:
        block.append(f"{hashtag_label}:\n{hashtags}")

    cta = guide.get("cta") or ""
    if cta:
        block.append(f"{cta_label}:\n{cta.strip()}")

    return "\n\n".join(block)


def _extract_dify_outputs(
    outputs: Dict[str, object],
    fallback_name: str,
    existing_product_name_cn: str,
) -> Dict[str, str]:
    market = outputs.get("market_strategy") or {}
    shooting = outputs.get("shooting_suggestion") or {}
    category = outputs.get("product_catogory_top3") or {}

    result: Dict[str, str] = {
        "product_name_cn": market.get("product_name_cn", ""),
        "selling_point": _format_bullet_points(market.get("selling_point_select_lan")),
        "selling_point_cn": _format_bullet_points(market.get("selling_point_cn")),
        "shooting_guide": _format_shooting_guides(shooting.get("shooting_guide_select_lan"), locale="default"),
        "shooting_guide_cn": _format_shooting_guides(shooting.get("shooting_guide_cn"), locale="cn"),
        "product_category_name": category.get("top_1", "") or "",
    }

    # Keep existing中文名 if Dify didn't provide one, otherwise留空用于标记失败
    if not result["product_name_cn"]:
        result["product_name_cn"] = existing_product_name_cn or ""
    return result


def _apply_enriched_records_to_batch(batch_id: int, records: List[Dict[str, Any]]) -> None:
    if not records:
        return
    ensure_product_schema()
    with get_session() as db:
        rows = (
            db.query(Product)
            .where(Product.batch_id == batch_id)
            .all()
        )
        mapping = {row.source_row_index: row for row in rows if row.source_row_index is not None}
        updated = 0
        for record in records:
            row_index = record.get("_row_index")
            if row_index is None:
                continue
            target = mapping.get(row_index)
            if not target:
                continue
            target.product_name_cn = record.get("product_name_cn", "") or target.product_name_cn or ""
            target.selling_point = record.get("selling_point", "") or target.selling_point or ""
            target.selling_point_cn = record.get("selling_point_cn", "") or target.selling_point_cn or ""
            target.shooting_guide = record.get("shooting_guide", "") or target.shooting_guide or ""
            target.shooting_guide_cn = record.get("shooting_guide_cn", "") or target.shooting_guide_cn or ""
            target.product_category_name = record.get("product_category_name", target.product_category_name or "")
            target.updated_at = now_beijing()
            updated += 1
        db.commit()
    if len(records) > 1:
        logger.info("Dify enrichment applied to batch %s, updated %s rows", batch_id, updated)


def enrich_product_batch_async(
    batch_id: int,
    filepath: Union[str, Path],
    *,
    override_region: Optional[str] = None,
) -> None:
    """
    重新跑 Dify 并将结果写入指定批次的 product 记录。供后台异步调用。
    """
    try:
        records, _ = _prepare_excel_records(filepath, override_region)
    except Exception as exc:
        logger.error("重新读取 Excel 失败(batch=%s): %s", batch_id, exc)
        return

    filtered: List[Dict[str, Any]] = []
    for record in records:
        if not record.get("product_link") and not record.get("product_id"):
            continue
        filtered.append(record)

    if not filtered:
        logger.warning("批次 %s 没有可用于 Dify 的记录", batch_id)
        return

    total = len(filtered)
    _update_batch_progress(batch_id, dify_total=total)

    def _handle_row(idx: int, enriched_record: Optional[Dict[str, Any]], success: bool, error: Optional[Exception]):
        if success and enriched_record:
            _apply_enriched_records_to_batch(batch_id, [enriched_record])
            _update_batch_progress(batch_id, processed_inc=1)
        else:
            _update_batch_progress(batch_id, processed_inc=1, failed_inc=1)

    try:
        _, failed = _enrich_records_with_dify(filtered, per_row_callback=_handle_row)
    except Exception as exc:
        logger.error("批次 %s 调用 Dify 失败: %s", batch_id, exc)
        return
    if failed:
        logger.warning("批次 %s 中以下行 Dify 失败: %s", batch_id, failed)


def _enrich_records_with_dify(
    rows: List[Dict[str, str]],
    per_row_callback: Optional[
        Callable[[int, Optional[Dict[str, Any]], bool, Optional[Exception]], None]
    ] = None,
) -> Tuple[List[Dict[str, str]], List[int]]:
    api_key = (
        os.getenv("DIFY_API_KEY_1104")
        or os.getenv("DIFY_API_KEY")
        or DifyConfig.api_key
    )
    api_base = (
        os.getenv("DIFY_API_BASE")
        or os.getenv("DIFY_BASE")
        or "https://api.dify.ai"
    )
    workflow_user = (
        os.getenv("DIFY_WORKFLOW_USER")
        or os.getenv("DIFY_USER_ID")
        or os.getenv("USER_ID")
        or DifyConfig.workflow_user
    )
    config = DifyConfig(api_base=api_base, api_key=api_key, workflow_user=workflow_user)
    client = DifyClient(config=config)

    failed_indices: List[int] = []

    try:
        enrichment_start = time.perf_counter()
        for idx, record in enumerate(rows):
            product_name = record.get("product_name", "")
            logger.info(
                "Dify enrichment start | row=%s | product=%s",
                idx,
                product_name,
            )

            if not record.get("product_name"):
                logger.info("Skip row %s due to missing product_name.", idx)
                failed_indices.append(idx)
                continue

            inputs = _build_dify_inputs(record, client)

            try:
                outputs = client.run_workflow(inputs)
            except DifyError as exc:
                logger.warning("Dify call failed for row %s (%s): %s", idx, product_name, exc)
                failed_indices.append(idx)
                if per_row_callback:
                    per_row_callback(idx, None, False, exc)
                continue

            record.update(
                _extract_dify_outputs(
                    outputs,
                    record.get("product_name", ""),
                    record.get("product_name_cn", ""),
                )
            )
            logger.info(
                "Dify enrichment done | row=%s | product=%s",
                idx,
                product_name,
            )
            if per_row_callback:
                per_row_callback(idx, record, True, None)

    finally:
        client.close()
        logger.info(
            "Dify enrichment finished | rows=%s | elapsed=%.2fs | failures=%s",
            len(rows),
            time.perf_counter() - enrichment_start,
            failed_indices,
        )

    return rows, failed_indices

def ingest_product_records(
    records: List[Dict[str, str]],
    uploaded_by: str,
    note: str = "",
    source_file: str = "",
    *,
    override_region: Optional[str] = None,
    total_rows: Optional[int] = None,
    dify_total: Optional[int] = None,
) -> Dict[str, int]:
    """
    直接使用 dict 列表导入商品。
    """
    if not records:
        return {"batch_id": None, "inserted": 0, "skipped": 0}

    ensure_product_schema()
    ensure_upload_batch_schema()

    with get_session() as db:
        batch = UploadBatch(
            uploaded_by=uploaded_by,
            source_file=source_file,
            note=note,
            uploaded_at=now_beijing(),
        )
        _init_batch_progress(
            batch,
            total_rows or len(records),
            dify_total or 0,
            override_region,
        )
        db.add(batch)
        db.flush()
        batch_id = batch.id

        inserted = 0
        skipped = 0

        for idx, r in enumerate(records):
            if not r.get("product_link") and not r.get("product_id"):
                skipped += 1
                continue

            now = now_beijing()
            row_index = r.get("_row_index", idx)
            fields = {
                "batch_id": batch_id,
                "source_row_index": row_index,
                "backend_system_id": r.get("backend_system_id", ""),
                "region": r.get("region", ""),
                "campaign_id": r.get("campaign_id", ""),
                "campaign_name": r.get("campaign_name", ""),
                "product_name": r.get("product_name", ""),
                "thumbnail": r.get("thumbnail", ""),
                "product_id": r.get("product_id", ""),
                "SKU_product": r.get("SKU_product", ""),
                "sale_price": r.get("sale_price", ""),
                "shop_name": r.get("shop_name", ""),
                "campaign_start_time": r.get("campaign_start_time", ""),
                "campaign_end_time": r.get("campaign_end_time", ""),
                "creator_rate": r.get("creator_rate", ""),
                "partner_rate": r.get("partner_rate", ""),
                "cost_product": r.get("cost_product", ""),
                "available_samples": r.get("available_samples", ""),
                "stock": r.get("stock", ""),
                "item_sold": r.get("item_sold", ""),
                "affiliate_link": r.get("affiliate_link", ""),
                "product_link": r.get("product_link", ""),
                "product_name_cn": r.get("product_name_cn", ""),
                "selling_point": r.get("selling_point", ""),
                "selling_point_cn": r.get("selling_point_cn", ""),
                "shooting_guide": r.get("shooting_guide", ""),
                "shooting_guide_cn": r.get("shooting_guide_cn", ""),
                "product_category_name": r.get("product_category_name", ""),
            }

            existing = None
            pid = fields["product_id"]
            if pid:
                stmt = select(Product).where(Product.product_id == pid).limit(1)
                existing = db.execute(stmt).scalars().first()
            if existing is None and row_index is not None:
                stmt = (
                    select(Product)
                    .where(
                        Product.batch_id == batch_id,
                        Product.source_row_index == row_index,
                    )
                    .limit(1)
                )
                existing = db.execute(stmt).scalars().first()

            if existing:
                for key, value in fields.items():
                    setattr(existing, key, value if value is not None else "")
                existing.updated_at = now
            else:
                prod = Product(
                    **fields,
                    created_at=now,
                    updated_at=now,
                )
                db.add(prod)
            inserted += 1

    return {
        "batch_id": batch_id,
        "inserted": inserted,
        "skipped": skipped,
        "total_rows": total_rows or len(records),
        "dify_total": dify_total or 0,
    }

def ingest_product_excel(
    filepath: Union[str, Path],
    uploaded_by: str,
    note: str = "",
    use_dify: bool = True,
    *,
    override_region: Optional[str] = None,
) -> Dict[str, int]:
    """
    读取 Excel -> 新建 UploadBatch -> 批量插入 Product。
    """
    filepath = Path(filepath)
    ensure_product_schema()
    records, df = _prepare_excel_records(filepath, override_region)
    for record in records:
        if not record.get("cost_product"):
            computed = _calc_cost_from_sale_price(record.get("sale_price", ""))
            if computed:
                record["cost_product"] = computed
    total_rows = len(records)
    dify_candidates = _count_dify_candidates(records)
    result = ingest_product_records(
        records,
        uploaded_by=uploaded_by,
        note=note,
        source_file=str(filepath),
        override_region=override_region,
        total_rows=total_rows,
        dify_total=dify_candidates,
    )
    if use_dify and dify_candidates:
        enrich_product_batch_async(
            result["batch_id"],
            filepath,
            override_region=override_region,
        )
    try:
        import pandas as pd

        enriched_df = pd.DataFrame(records)
        column_order = list(df.columns)
        for col in DIFY_OUTPUT_COLUMNS:
            if col not in column_order:
                column_order.append(col)
        enriched_df = enriched_df.reindex(columns=column_order)
        output_name = f"{filepath.stem}_raw{filepath.suffix}"
        output_path = PRODUCT_DATA_DIR / output_name
        enriched_df.to_excel(output_path, index=False)
        logger.info("保存处理后的 Excel：%s", output_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("导出 Excel 失败: %s", exc)

    return result

def ingest_default_product_excel(
    uploaded_by: str = "system",
    note: str = "default import",
    use_dify: bool = True,
    override_region: Optional[str] = None,
) -> Dict[str, int]:
    """
    使用默认路径 data/product_data/product_list.xlsx 导入商品数据。
    """
    if not DEFAULT_PRODUCT_EXCEL.exists():
        legacy_path = DATA_DIR / "product" / "product_list.xlsx"
        if legacy_path.exists():
            return ingest_product_excel(
                legacy_path,
                uploaded_by=uploaded_by,
                note=note,
                use_dify=use_dify,
                override_region=override_region,
            )
        raise FileNotFoundError(
            f"未找到默认的 product_list.xlsx，期望位置：{DEFAULT_PRODUCT_EXCEL}（如仍放在 data/product/ 下，请移动或设置 DB_URL）"
        )
    return ingest_product_excel(
        DEFAULT_PRODUCT_EXCEL,
        uploaded_by=uploaded_by,
        note=note,
        use_dify=use_dify,
        override_region=override_region,
    )

def get_default_product_excel_path() -> Path:
    """
    返回默认商品清单所在位置，供外部检查或写入。
    """
    return DEFAULT_PRODUCT_EXCEL

def get_product_data_dir() -> Path:
    """
    返回商品数据目录。
    """
    return PRODUCT_DATA_DIR
