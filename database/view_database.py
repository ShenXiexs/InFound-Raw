# database/view_database.py
"""
多功能数据库查看脚本。
支持列出表、统计行数、查看前 N 行以及执行只读 SQL。
"""
from __future__ import annotations

import argparse
from typing import List, Optional

from sqlalchemy import text, inspect

from database.db import get_session, engine
from database.models import Creator, CreatorLog, Product

DEFAULT_SAMPLE_TABLES = {
    "creator": Creator,
    "creator_log": CreatorLog,
    "product": Product,
}

def list_tables() -> List[str]:
    inspector = inspect(engine)
    return sorted(inspector.get_table_names())

def count_rows(tables: Optional[List[str]] = None):
    with get_session() as db:
        names = tables or list_tables()
        for name in names:
            try:
                total = db.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
                print(f"{name}: {total}")
            except Exception as exc:
                print(f"{name}: <error> {exc}")

def show_head(table: str, limit: int = 5):
    with get_session() as db:
        print(f"=== {table} (limit {limit}) ===")
        try:
            rows = db.execute(text(f"SELECT * FROM {table} LIMIT :limit"), {"limit": limit}).mappings().all()
        except Exception as exc:
            print(f"读取 {table} 失败: {exc}")
            return
        if not rows:
            print("无记录")
            return
        for row in rows:
            print(dict(row))

def run_sql(sql: str):
    with get_session() as db:
        try:
            result = db.execute(text(sql))
            rows = result.mappings().all()
        except Exception as exc:
            print(f"SQL 执行失败: {exc}")
            return
        if not rows:
            print("无结果")
            return
        for row in rows:
            print(dict(row))

def main():
    parser = argparse.ArgumentParser(description="多功能数据库查看工具")
    parser.add_argument("--tables", action="store_true", help="列出所有表名")
    parser.add_argument("--count", nargs="*", help="统计表行数（默认全部表）")
    parser.add_argument("--head", nargs="*", help="查看表前 N 行，格式 table[:N]")
    parser.add_argument("--sql", help="执行自定义只读 SQL")
    parser.add_argument("--summary", action="store_true", help="输出常用表的行数和样例")
    args = parser.parse_args()

    any_action = any([args.tables, args.count is not None, args.head, args.sql, args.summary])
    if not any_action:
        parser.print_help()
        return

    if args.tables:
        print("表名：")
        for name in list_tables():
            print(f"- {name}")

    if args.count is not None:
        print("行数统计：")
        count_rows(args.count if args.count else None)

    if args.head:
        for item in args.head:
            if ":" in item:
                table, _, limit_str = item.partition(":")
                try:
                    limit = int(limit_str)
                except ValueError:
                    limit = 5
            else:
                table = item
                limit = 5
            show_head(table, limit)

    if args.sql:
        print(f"执行 SQL: {args.sql}")
        run_sql(args.sql)

    if args.summary:
        print("摘要：")
        for table_name, model in DEFAULT_SAMPLE_TABLES.items():
            with get_session() as db:
                total = db.query(model).count()
                print(f"{table_name}: {total}")
                rows = db.query(model).limit(3).all()
                for row in rows:
                    data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
                    print(data)

if __name__ == "__main__":
    main()
