# ====================================================================
# PHASE 1: BUILDER STAGE (安装依赖)
# --------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

# 设置构建参数和服务名称
ARG SERVICE_NAME=service-a
ENV SERVICE_NAME=${SERVICE_NAME}
ENV PYTHONUNBUFFERED=1

# 安装系统依赖 (用于编译一些 Python 包)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    # 确保根据你的依赖 (如 asyncmy) 包含必要的库
    libmariadb-dev-compat \
    # 安装 git 方便 Poetry 安装 git 依赖 (如果需要)
    git \
    && rm -rf /var/lib/apt/lists/*

# 安装 Poetry
# 由于你要求 >=3.13，确保安装兼容的 Poetry 版本
RUN pip install poetry==2.2.1

WORKDIR /app

# 复制项目配置文件
COPY pyproject.toml poetry.lock /app/

# (可选) 复制通用依赖脚本
#COPY requirements.txt /app/
#COPY --chown=root:root apps/${SERVICE_NAME}/requirements.${SERVICE_NAME}.txt* /app/

# 在 builder 阶段明确指定虚拟环境路径
RUN poetry config virtualenvs.in-project true

# 安装所有依赖（--only main 只安装主要依赖，不包括 dev 组）
# --no-root 表示不安装项目本身作为一个包
# Poetry 会根据 pyproject.toml 和 poetry.lock 安装依赖
RUN poetry install --no-root --only main --sync

# ====================================================================
# PHASE 2: RUNNER STAGE (精简运行环境)
# --------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runner

ARG SERVICE_NAME=service-a
ENV SERVICE_NAME=${SERVICE_NAME}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/apps

WORKDIR /app

# 从 builder 阶段复制 Poetry 安装的虚拟环境
# 注意：路径可能因 Poetry 版本或安装位置而异，这里使用默认的 .venv
COPY --from=builder /usr/local/bin/poetry /usr/local/bin/poetry
# COPY --from=builder $(poetry env info --path) /usr/local/lib/python3.13/site-packages
COPY --from=builder /app/.venv /app/.venv

# 将虚拟环境的路径添加到 PATH，确保 Gunicorn 运行在正确的环境中
ENV PATH="/app/.venv/bin:$PATH"

# 复制项目核心代码和配置文件
COPY main.py /app/
COPY common/ /app/common/
COPY configs/ /app/configs/
COPY apps/${SERVICE_NAME}/ /app/apps/${SERVICE_NAME}/

# 创建日志目录
RUN mkdir -p /app/logs && chmod 777 /app/logs

EXPOSE 8000

# ----------------- 启动命令 (Gunicorn + Uvicorn Worker) -----------------
# 假设应用实例在 apps/${SERVICE_NAME}/main.py 文件中被命名为 app
# Gunicorn worker 数量 (例如 4 个) 应该根据你的生产环境 CPU 核数进行调整
# 修改最后一行 CMD 指令为：
CMD ["sh", "-c", "gunicorn -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --log-level info main:app"]
# -----------------------------------------------------------------------