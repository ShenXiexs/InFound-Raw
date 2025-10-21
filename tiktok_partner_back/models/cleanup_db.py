import sqlite3

db_path = "data/record/central_record.db"

with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()

    # 清空所有任务
    cursor.execute("DELETE FROM tasks")

    # 清空达人记录
    # cursor.execute("DELETE FROM creator_records")

    conn.commit()

print("已清空 tasks")
