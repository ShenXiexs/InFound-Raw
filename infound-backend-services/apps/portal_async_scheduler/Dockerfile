# ====================================================================
# PHASE 1: BUILDER STAGE (安装依赖)
# --------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1 \
    PIP_CACHE_DIR=/tmp/pip-cache

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    libmariadb-dev-compat \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install uv>=0.9.26

WORKDIR /app

# 复制根项目配置（用于 workspace 依赖解析）
COPY pyproject.toml uv.lock /app/

# 复制所有 packages（workspace 依赖）
COPY packages/ /app/packages/

# 复制当前服务代码（保持 apps 目录结构）
COPY apps/portal_async_scheduler/ /app/apps/portal_async_scheduler/

# 使用 uv sync 命令安装依赖，并验证锁文件
RUN uv sync --frozen --no-dev --package portal-async-scheduler

# ====================================================================
# PHASE 2: RUNNER STAGE (精简运行环境)
# --------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Shanghai

WORKDIR /app

# 设置时区
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 从 builder 复制虚拟环境
COPY --from=builder /app/.venv /app/.venv

# 设置 PATH
ENV PATH="/app/.venv/bin:$PATH"

ARG BUILD_DATE=unknown
LABEL build_version=${BUILD_DATE}

# 复制服务代码（保持 apps 目录结构）
COPY apps/portal_async_scheduler/ /app/apps/portal_async_scheduler/

# 复制 packages（运行时依赖）
COPY packages/ /app/packages/

# 创建日志目录并设置权限（关键修改：使用777权限）
RUN mkdir -p /app/logs && chmod 777 /app/logs

# 启动命令使用 uv run（推荐方式）
CMD ["python", "apps/portal_async_scheduler/main.py"]
