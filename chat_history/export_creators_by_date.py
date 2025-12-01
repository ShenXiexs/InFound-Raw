#!/usr/bin/env python
"""
Filter creator_GOKOCO.MX.xlsx by send_time and export region-specific files.

Usage:
    python scripts/export_creators_by_date.py --date 20251112
    python scripts/export_creators_by_date.py --date 20251112 --input data/creator_GOKOCO.MX.xlsx --output-dir data/chat_history_date
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Creator list slicer by send_time.")
    parser.add_argument(
        "--date",
        required=True,
        help="截止日期，格式 YYYYMMDD（例如 20251101 表示 2025-11-01 00:00 前）",
    )
    parser.add_argument(
        "--input",
        default="data/creator_GOKOCO.MX.xlsx",
        help="源 Excel 路径，默认 data/creator_GOKOCO.MX.xlsx",
    )
    parser.add_argument(
        "--output-dir",
        default="data/chat_history",
        help="导出目录，默认 data/chat_history",
    )
    return parser.parse_args()


def _normalize_region(value: Optional[str]) -> str:
    if not value:
        return "UNKNOWN"
    return str(value).strip().upper() or "UNKNOWN"


def main() -> None:
    args = _parse_args()
    cutoff_date = datetime.strptime(args.date, "%Y%m%d")
    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    df = pd.read_excel(input_path, engine="openpyxl")
    if "send_time" not in df.columns:
        raise ValueError("Excel 缺少 send_time 列")
    if "creator_name" not in df.columns:
        raise ValueError("Excel 缺少 creator_name 列")
    if "region" not in df.columns:
        raise ValueError("Excel 缺少 region 列")

    parsed_times = pd.to_datetime(df["send_time"], errors="coerce")
    last_idx = -1
    for idx, ts in enumerate(parsed_times):
        if pd.notna(ts) and ts < cutoff_date:
            last_idx = idx

    if last_idx == -1:
        print(f"没有 send_time 早于 {cutoff_date.isoformat()} 的达人，未导出文件。")
        return

    subset = df.iloc[: last_idx + 1].copy()
    subset = subset.drop_duplicates(subset="creator_name", keep="last")
    subset["region"] = subset["region"].apply(_normalize_region)

    output_dir.mkdir(parents=True, exist_ok=True)
    exported = 0
    for region_value in sorted(subset["region"].unique()):
        region_df = subset[subset["region"] == region_value]
        if region_df.empty:
            continue
        safe_region = region_value.replace(" ", "_")
        output_path = output_dir / f"creator_{args.date}_{safe_region}.xlsx"
        region_df.to_excel(output_path, index=False, engine="openpyxl")
        print(f"已导出 {len(region_df)} 条记录 -> {output_path}")
        exported += 1

    if exported == 0:
        print("筛选结果为空，未生成文件。")


if __name__ == "__main__":
    main()
