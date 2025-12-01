# database/ingest_creator_excel.py
"""
将 data 目录中的达人 Excel 快照导入数据库。
默认顺序认为越靠后的行越新，因此按顺序逐行写入，最终保留最新状态在 Creator 表，所有记录写入 CreatorLog。
"""
from __future__ import annotations

from typing import Dict, Any, Optional, Iterable
from pathlib import Path
from datetime import datetime

import pandas as pd

from database.ingest_creator_data import log_creator_snapshot_to_db

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CREATOR_EXCEL = DATA_DIR / "creator_GOKOCO.MX.xlsx"

BOOL_TRUE = {"1", "true", "yes", "y", "t", "on"}
NUMERIC_FIELDS = {
    "followers",
    "avg_video_views",
    "avg_live_views",
}

def _parse_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        val = value.strip().lower()
        if not val:
            return None
        if val in BOOL_TRUE:
            return True
        if val in {"0", "false", "no", "n", "f", "off"}:
            return False
    return None

def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        stripped = value.replace(",", "").strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except (TypeError, ValueError):
            return None
    return None

def _clean_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    row = {k: ("" if pd.isna(v) else v) for k, v in raw.items()}

    # 兼容常见拼写错误
    if "camampaign_id" in row and "campaign_id" not in row:
        row["campaign_id"] = row.pop("camampaign_id")

    for field in NUMERIC_FIELDS:
        row[field] = _parse_int(row.get(field))

    for bool_field in ("connect", "reply", "send"):
        parsed = _parse_bool(row.get(bool_field))
        row[bool_field] = parsed

    # 统一字符串化其余字段，保持与原逻辑兼容
    for key, value in row.items():
        if key in NUMERIC_FIELDS:
            continue
        if key in {"connect", "reply", "send"}:
            continue
        if isinstance(value, datetime):
            row[key] = value.isoformat()
        elif value is None or pd.isna(value):
            row[key] = ""
        else:
            row[key] = str(value).strip()

    return row

def ingest_creator_excel(
    filepath: Path | str = DEFAULT_CREATOR_EXCEL,
    *,
    task_id: Optional[str] = None,
    shop_name: Optional[str] = None,
    show_progress: bool = True,
) -> Dict[str, int]:
    """
    将 Excel 导入数据库。

    Args:
        filepath: Excel 文件路径
        task_id: 任务标识。默认取文件名（无扩展名）
        shop_name: 店铺/任务名称，默认使用 brand_name 或 'ExcelImport'
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"未找到达人 Excel：{filepath}")

    df = pd.read_excel(filepath, dtype=str)
    df = df.fillna("")
    records: Iterable[Dict[str, Any]] = df.to_dict(orient="records")

    total = len(records)
    imported = 0
    skipped = 0

    derived_task_id = task_id or filepath.stem

    if show_progress:
        print(f"开始导入达人 Excel：{filepath}，共 {total} 行")

    for index, raw in enumerate(records, start=1):
        row = _clean_row(raw)
        creator_id = row.get("creator_id")
        if not creator_id:
            skipped += 1
            continue

        current_shop = shop_name or row.get("shop_name") or row.get("brand_name") or "ExcelImport"
        try:
            log_creator_snapshot_to_db(
                row,
                task_id=derived_task_id,
                shop_name=current_shop,
            )
            imported += 1
            if show_progress and (index % 50 == 0 or index == total):
                print(f"进度：{index}/{total} 行，成功 {imported}，跳过 {skipped}")
        except Exception as exc:
            skipped += 1
            print(f"[WARN] 导入达人 {creator_id} 失败：{exc}")

    return {"imported": imported, "skipped": skipped}

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="将达人 Excel 导入数据库")
    parser.add_argument("--file", dest="file", default=str(DEFAULT_CREATOR_EXCEL), help="Excel 文件路径")
    parser.add_argument("--task-id", dest="task_id", default=None, help="写入 CreatorLog 的 task_id")
    parser.add_argument("--shop-name", dest="shop_name", default=None, help="写入 CreatorLog 的 shop_name")
    parser.add_argument("--silent", action="store_true", help="关闭进度输出")
    args = parser.parse_args()

    summary = ingest_creator_excel(
        filepath=args.file,
        task_id=args.task_id,
        shop_name=args.shop_name,
        show_progress=not args.silent,
    )
    print("导入完成：", summary)
