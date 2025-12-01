# database/ingest_task_info.py

from database.db import get_session, engine, now_beijing
from database.models import OutreachTask
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

def log_task_info_to_db(row_data: dict):
    """
    把 save_task_info() 里整理出来的 row_data 写进 outreach_task 表。
    如果 task_id 已经存在，就直接 return（和你 Excel 逻辑保持一致）。
    如果不存在，就插入一条。
    """

    ensure_outreach_task_schema()

    with get_session() as db:
        task_id = str(row_data.get("task_id"))
        try:
            existing = db.query(OutreachTask).filter(OutreachTask.task_id == task_id).first()
        except OperationalError:
            ensure_outreach_task_schema(force_refresh=True)
            existing = db.query(OutreachTask).filter(OutreachTask.task_id == task_id).first()

        if existing:
            return  # 和Excel逻辑保持一致：存在就不重复写

        task = OutreachTask(
            task_id=task_id,
            task_name=row_data.get("task_name"),
            campaign_id=row_data.get("campaign_id"),
            campaign_name=row_data.get("campaign_name"),
            product_id=row_data.get("product_id"),
            product_name=row_data.get("product_name"),
            region=row_data.get("region"),
            brand=row_data.get("brand"),
            only_first=str(row_data.get("only_first")),
            task_type=row_data.get("task_type", "Connect"),
            search_keywords=_normalize(row_data.get("search_keywords")),
            product_category=_normalize(row_data.get("product_category")),
            fans_age_range=_normalize(row_data.get("fans_age_range")),
            fans_gender=row_data.get("fans_gender"),
            min_fans=row_data.get("min_fans"),
            content_type=_normalize(row_data.get("content_type")),
            gmv=_normalize(row_data.get("gmv")),
            sales=_normalize(row_data.get("sales")),
            min_GMV=row_data.get("min_GMV"),
            max_GMV=row_data.get("max_GMV"),
            avg_views=row_data.get("avg_views"),
            min_engagement_rate=row_data.get("min_engagement_rate"),
            email_first_subject=row_data.get("email_first_subject"),
            email_first_body=row_data.get("email_first_body"),
            email_later_subject=row_data.get("email_later_subject"),
            email_later_body=row_data.get("email_later_body"),
            target_new_creators=row_data.get("target_new_creators"),
            max_creators=row_data.get("max_creators"),
            run_at_time=row_data.get("run_at_time"),
            run_end_time=row_data.get("run_end_time"),
            run_time=row_data.get("run_time"),
            task_directory=row_data.get("task_directory"),
            connect_creator=row_data.get("connect_creator"),
            new_creators=row_data.get("new_creators"),
            created_at=now_beijing(),  # 统一存北京时间
        )

        db.add(task)


def _normalize(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value

_schema_checked = False

def ensure_outreach_task_schema(force_refresh: bool = False):
    """
    确保 outreach_task 表包含最新需要的列。
    在早期数据库未添加 max_GMV 列的情况下，自动补齐。
    """
    global _schema_checked
    if _schema_checked and not force_refresh:
        return

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("outreach_task")}
    missing_alters = []
    schema_updates = {
        "max_GMV": "ALTER TABLE outreach_task ADD COLUMN max_GMV TEXT",
        "gmv": "ALTER TABLE outreach_task ADD COLUMN gmv TEXT",
        "sales": "ALTER TABLE outreach_task ADD COLUMN sales TEXT",
        "task_type": "ALTER TABLE outreach_task ADD COLUMN task_type TEXT DEFAULT 'Connect'",
        "status": "ALTER TABLE outreach_task ADD COLUMN status TEXT DEFAULT 'pending'",
        "message": "ALTER TABLE outreach_task ADD COLUMN message TEXT",
        "created_by": "ALTER TABLE outreach_task ADD COLUMN created_by TEXT",
        "account_email": "ALTER TABLE outreach_task ADD COLUMN account_email TEXT",
        "log_path": "ALTER TABLE outreach_task ADD COLUMN log_path TEXT",
        "output_files": "ALTER TABLE outreach_task ADD COLUMN output_files TEXT",
        "total_creators": "ALTER TABLE outreach_task ADD COLUMN total_creators INTEGER",
        "payload_json": "ALTER TABLE outreach_task ADD COLUMN payload_json TEXT",
        "started_at": "ALTER TABLE outreach_task ADD COLUMN started_at TEXT",
        "finished_at": "ALTER TABLE outreach_task ADD COLUMN finished_at TEXT",
    }

    for column, statement in schema_updates.items():
        if column not in columns:
            missing_alters.append(statement)

    if missing_alters:
        with engine.begin() as conn:
            for stmt in missing_alters:
                conn.execute(text(stmt))

    _schema_checked = True
