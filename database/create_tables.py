# database/create_tables.py
from database.db import engine, Base
import database.models  # noqa: F401  确保模型加载

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print(" tables created.")
