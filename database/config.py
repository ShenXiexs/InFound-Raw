# database/config.py
import os
from pathlib import Path

# 允许 .env（本地）和真实环境变量（线上）
ENV_PATH = Path(__file__).resolve().parent / ".env"
if ENV_PATH.exists():
    # 轻量 .env 解析，避免额外依赖
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"): 
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "infound_dev.db"
DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# 优先读取环境变量；否则落到仓库内 data/infound_dev.db
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    DB_URL = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"

ECHO_SQL = os.getenv("ECHO_SQL", "0") == "1"                # 调试用，打印SQL
