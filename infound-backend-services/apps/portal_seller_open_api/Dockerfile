# ====================================================================
# PHASE 1: BUILDER STAGE (安装依赖)
# --------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    libmariadb-dev-compat \
    git \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install uv>=0.9.26

WORKDIR /app

# 复制根项目配置（用于 workspace 依赖解析）
COPY pyproject.toml uv.lock /app/

# 复制所有 packages（workspace 依赖）
COPY packages/ /app/packages/

# 复制当前服务代码（保持 apps 目录结构）
COPY apps/portal_seller_open_api/ /app/apps/portal_seller_open_api/

# 安装依赖
RUN uv sync --frozen --no-dev --package portal-seller-open-api

# 额外安装 gunicorn
RUN pip install gunicorn>=23.0.0

# ====================================================================
# PHASE 2: RUNNER STAGE (精简运行环境)
# --------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# 从 builder 复制虚拟环境
COPY --from=builder /app/.venv /app/.venv

# 设置 PATH
ENV PATH="/app/.venv/bin:$PATH"

ARG BUILD_DATE=unknown
LABEL build_version=${BUILD_DATE}

# 复制服务代码（保持 apps 目录结构）
COPY apps/portal_seller_open_api/ /app/apps/portal_seller_open_api/

# 复制 packages（运行时依赖）
COPY packages/ /app/packages/

# 创建日志目录
RUN mkdir -p /app/logs && chmod 777 /app/logs

EXPOSE 8000

# 启动命令
CMD ["sh", "-c", "gunicorn -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --log-level info apps.portal_seller_open_api.main:app"]
