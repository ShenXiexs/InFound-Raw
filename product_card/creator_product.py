from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CREATOR_FILE = BASE_DIR / "data" / "card" / "creator_info.xlsx"
DEFAULT_PRODUCT_FILE = BASE_DIR / "data" / "card" / "product_info.xlsx"
DEFAULT_OUTPUT_DIR = BASE_DIR / "data" / "card"
LATEST_JSON_PATH = DEFAULT_OUTPUT_DIR / "card_send_list.json"


def _safe_string(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def generate_card_send_list(
    creator_file: Path,
    product_file: Path,
    output_dir: Optional[Path] = None,
    output_filename: Optional[str] = None,
    update_latest: bool = False,
) -> Dict[str, object]:
    """
    根据达人&产品两个 Excel 文件生成 card_send_list JSON。

    Args:
        creator_file: 达人 Excel 路径，需包含 creator_name / creator_id 列
        product_file: 商品 Excel 路径，需包含 campaign_id / product_id / rate / message 列
        output_dir: JSON 输出目录，默认 data/card
        output_filename: 自定义输出文件名，默认 card_send_list_YYYYMMDD.json
        update_latest: 是否同时覆盖 data/card/card_send_list.json

    Returns:
        dict: {
            "output_file": str,
            "record_count": int,
            "card_send_list": List[dict]
        }
    """
    creator_path = Path(creator_file).expanduser().resolve()
    product_path = Path(product_file).expanduser().resolve()
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not creator_path.exists():
        raise FileNotFoundError(f"未找到达人文件: {creator_path}")
    if not product_path.exists():
        raise FileNotFoundError(f"未找到商品文件: {product_path}")

    creator_df = pd.read_excel(creator_path)
    product_df = pd.read_excel(product_path)

    required_creator_columns = {"creator_name", "creator_id"}
    required_product_columns = {"campaign_id", "product_id", "rate", "message"}
    if missing := required_creator_columns - set(creator_df.columns):
        raise ValueError(f"达人 Excel 缺少必要列: {', '.join(sorted(missing))}")
    if missing := required_product_columns - set(product_df.columns):
        raise ValueError(f"商品 Excel 缺少必要列: {', '.join(sorted(missing))}")

    grouped_products: Dict[str, Dict[str, List[str]]] = {}
    for campaign_id, group in product_df.groupby("campaign_id"):
        product_ids = [_safe_string(pid) for pid in group["product_id"]]
        rates = [_safe_string(rate) for rate in group["rate"]]
        message_value = _safe_string(group["message"].iloc[0]) if len(group) else ""

        grouped_products[str(campaign_id)] = {
            "product_ids": [pid for pid in product_ids if pid],
            "rate": [rate for rate in rates if rate],
            "message": message_value,
        }

    card_send_list: List[Dict[str, object]] = []
    for _, creator in creator_df.iterrows():
        creator_name = _safe_string(creator.get("creator_name"))
        creator_id = _safe_string(creator.get("creator_id"))
        if not creator_name or not creator_id:
            continue

        for campaign_id, product_info in grouped_products.items():
            if not product_info["product_ids"]:
                continue
            card_send_list.append(
                {
                    "creator_name": creator_name,
                    "creator_id": creator_id,
                    "campaign_id": str(campaign_id),
                    "product_ids": product_info["product_ids"],
                    "rate": product_info["rate"],
                    "message": product_info["message"],
                }
            )

    if output_filename:
        output_name = output_filename
    else:
        date_suffix = datetime.now().strftime("%Y%m%d")
        output_name = f"card_send_list_{date_suffix}.json"
    output_path = output_dir / output_name

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(card_send_list, f, ensure_ascii=False, indent=2)

    if update_latest:
        shutil.copy2(output_path, LATEST_JSON_PATH)

    return {
        "output_file": str(output_path),
        "record_count": len(card_send_list),
        "card_send_list": card_send_list,
    }


def main():
    parser = argparse.ArgumentParser(description="生成商品卡发送 JSON")
    parser.add_argument(
        "--creator-file",
        type=Path,
        default=DEFAULT_CREATOR_FILE,
        help="达人 Excel 路径，默认 data/card/creator_info.xlsx",
    )
    parser.add_argument(
        "--product-file",
        type=Path,
        default=DEFAULT_PRODUCT_FILE,
        help="商品 Excel 路径，默认 data/card/product_info.xlsx",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="输出目录，默认 data/card",
    )
    parser.add_argument(
        "--output-name",
        type=str,
        default=None,
        help="自定义输出文件名，默认 card_send_list_YYYYMMDD.json",
    )
    parser.add_argument(
        "--update-latest",
        action="store_true",
        help="同步覆盖 data/card/card_send_list.json",
    )
    args = parser.parse_args()

    result = generate_card_send_list(
        creator_file=args.creator_file,
        product_file=args.product_file,
        output_dir=args.output_dir,
        output_filename=args.output_name,
        update_latest=args.update_latest,
    )

    print(f"成功生成文件: {result['output_file']}")
    print(f"共生成 {result['record_count']} 条记录")


if __name__ == "__main__":
    main()
