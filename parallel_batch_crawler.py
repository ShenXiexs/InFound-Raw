#!/usr/bin/env python3
"""
命令行批量触发爬虫任务
读取单个 JSON 配置并通过新的任务管理器执行，适用于服务器上手动调试。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from schemas.crawler import CrawlerTaskCreateRequest
from services.crawler_service import get_crawler_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动单个爬虫任务")
    parser.add_argument(
        "--config",
        required=True,
        help="任务配置 JSON 文件路径（格式与 API 相同）",
    )
    parser.add_argument("--user", default="cli", help="创建任务的用户名标识")
    parser.add_argument("--max-creators", type=int, help="覆盖默认的最大达人数量")
    parser.add_argument("--target-new", type=int, help="覆盖默认的目标新增达人数量")
    parser.add_argument("--poll-interval", type=int, default=10, help="状态轮询间隔（秒）")
    return parser.parse_args()


def load_request(config_path: Path, overrides: dict) -> CrawlerTaskCreateRequest:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload.update({k: v for k, v in overrides.items() if v is not None})
    return CrawlerTaskCreateRequest(**payload)


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[错误] 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    overrides = {
        "max_creators": args.max_creators,
        "target_new_creators": args.target_new,
    }

    request = load_request(config_path, overrides)
    service = get_crawler_service()
    task_id = service.submit_task(request, created_by=args.user)
    print(
        f"[信息] 已提交任务 {task_id}，开始轮询状态… "
        f"(max_creators={request.max_creators}, target_new_creators={request.target_new_creators})"
    )

    while True:
        status = service.get_task(task_id)
        if not status:
            print("[错误] 未找到任务，可能被删除。", file=sys.stderr)
            sys.exit(1)

        print(
            f"[状态] {status.status.upper()} | message={status.message} | "
            f"new={status.new_creators} | account={status.account_email}"
        )

        if status.status in {"completed", "failed", "cancelled"}:
            print(f"[完成] 任务 {task_id} 状态: {status.status}")
            if status.log_path:
                print(f"[日志] {status.log_path}")
            if status.output_files:
                print("[输出]")
                for file_path in status.output_files:
                    print(f"  - {file_path}")
            break

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
