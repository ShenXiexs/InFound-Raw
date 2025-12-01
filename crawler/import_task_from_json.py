#!/usr/bin/env python
"""
从 task_json/*.json 导入一条建联任务，仅写入 outreach_task 表，不触发执行。
用法：
    python scripts/import_task_from_json.py --file task_json/papafeel.json --task-id manual-20231118-001
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from database.db import get_session, now_beijing
from database.models import OutreachTask


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _extract_brand(payload: Dict[str, Any]) -> Dict[str, str]:
    brand = payload.get("brand") or {}
    return {
        "name": str(brand.get("name") or ""),
        "only_first": str(brand.get("only_first") or ""),
        "key_word": str(brand.get("key_word") or ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import outreach task from JSON file")
    parser.add_argument("--file", required=True, help="Path to task_json file")
    parser.add_argument("--task-id", default=None, help="Override task_id (defaults to json field or文件名)")
    parser.add_argument("--status", default=None, help="Override status (默认使用 json->status 或 completed)")
    parser.add_argument("--new-creators", type=int, default=None, help="Override new_creators")
    parser.add_argument("--created-by", default="system", help="记录 created_by 字段")
    parser.add_argument("--overwrite", action="store_true", help="如任务已存在则覆盖更新")
    args = parser.parse_args()

    file_path = Path(args.file).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path} 不存在")

    payload = _load_json(file_path)

    task_id = args.task_id or payload.get("task_id") or file_path.stem
    status = args.status or payload.get("status") or "completed"
    new_creators = args.new_creators
    if new_creators is None:
        new_creators = payload.get("new_creators")

    brand_info = _extract_brand(payload)

    data = OutreachTask(
        task_id=task_id,
        task_name=payload.get("task_name", ""),
        campaign_id=payload.get("campaign_id", ""),
        campaign_name=payload.get("campaign_name", ""),
        product_id=str(payload.get("product_id") or ""),
        product_name=payload.get("product_name", ""),
        region=payload.get("region", ""),
        brand=brand_info["name"],
        only_first=brand_info["only_first"],
        task_type=payload.get("task_type", "Connect"),
        status=status,
        message=str(payload.get("message") or ""),
        created_by=args.created_by,
        account_email=payload.get("account_email", ""),
        search_keywords=payload.get("search_strategy", {}).get("search_keywords", ""),
        product_category=",".join(payload.get("search_strategy", {}).get("product_category", []) or []),
        fans_age_range=",".join(payload.get("search_strategy", {}).get("fans_age_range", []) or []),
        fans_gender=str(payload.get("search_strategy", {}).get("fans_gender") or ""),
        min_fans=str(payload.get("search_strategy", {}).get("min_fans") or ""),
        content_type=",".join(payload.get("search_strategy", {}).get("content_type", []) or []),
        gmv=",".join(payload.get("search_strategy", {}).get("gmv", []) or []),
        sales=",".join(payload.get("search_strategy", {}).get("sales", []) or []),
        avg_views=str(payload.get("search_strategy", {}).get("avg_views") or ""),
        min_engagement_rate=str(payload.get("search_strategy", {}).get("min_engagement_rate") or ""),
        email_first_subject=payload.get("email_first", {}).get("subject", ""),
        email_first_body=payload.get("email_first", {}).get("email_body", ""),
        email_later_subject=payload.get("email_later", {}).get("subject", ""),
        email_later_body=payload.get("email_later", {}).get("email_body", ""),
        target_new_creators=payload.get("target_new_creators"),
        max_creators=payload.get("max_creators"),
        new_creators=new_creators,
        payload_json=json.dumps(payload, ensure_ascii=False),
        created_at=now_beijing(),
    )

    with get_session() as db:
        existing = db.get(OutreachTask, task_id)
        if existing and not args.overwrite:
            raise ValueError(f"task_id={task_id} 已存在，终止导入（如需覆盖请加 --overwrite）")
        if existing and args.overwrite:
            for field in data.__table__.columns.keys():
                setattr(existing, field, getattr(data, field))
            db.add(existing)
        else:
            db.add(data)
        db.commit()

    print(f"任务 {task_id} 已写入 outreach_task 表，status={status}, new_creators={new_creators}")


if __name__ == "__main__":
    main()
