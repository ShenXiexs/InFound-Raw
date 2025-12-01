# database/db.py
# database/db.py
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from database.config import DB_URL, ECHO_SQL

# SQLite 需要 check_same_thread=False（仅SQLite）
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, echo=ECHO_SQL, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
    expire_on_commit=False,
)
Base = declarative_base()

def now_beijing() -> datetime:
    """统一使用北京时间 (+08:00)。"""
    return datetime.now(timezone(timedelta(hours=8)))

@contextmanager
def get_session():
    """with get_session() as db: db.query(...); db.add(...);"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
