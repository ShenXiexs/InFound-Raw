# ====================================================================
# PHASE 1: BUILDER STAGE (install deps)
# --------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

# Build args and service name
ARG SERVICE_NAME=service-a
ENV SERVICE_NAME=${SERVICE_NAME}
ENV PYTHONUNBUFFERED=1

# System deps (for building Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    # Include libs required by dependencies (e.g., asyncmy)
    libmariadb-dev-compat \
    # Git for Poetry git dependencies (if needed)
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (>=3.13-compatible)
RUN pip install poetry==2.2.1

WORKDIR /app

# Copy project config files
COPY pyproject.toml poetry.lock /app/

# (Optional) copy shared requirements
#COPY requirements.txt /app/
#COPY --chown=root:root apps/${SERVICE_NAME}/requirements.${SERVICE_NAME}.txt* /app/

# Pin venv location in builder stage
RUN poetry config virtualenvs.in-project true

# Install dependencies (--only main excludes dev; --no-root skips project package)
RUN poetry install --no-root --only main --sync

# ====================================================================
# PHASE 2: RUNNER STAGE (runtime image)
# --------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runner

ARG SERVICE_NAME=service-a
ENV SERVICE_NAME=${SERVICE_NAME}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/apps

WORKDIR /app

# Copy Poetry venv from builder stage
# NOTE: path may vary by Poetry version; using default .venv
COPY --from=builder /usr/local/bin/poetry /usr/local/bin/poetry
# COPY --from=builder $(poetry env info --path) /usr/local/lib/python3.13/site-packages
COPY --from=builder /app/.venv /app/.venv

# Add venv to PATH so Gunicorn uses correct env
ENV PATH="/app/.venv/bin:$PATH"

# Copy core code and configs
COPY main.py /app/
COPY common/ /app/common/
COPY configs/ /app/configs/
COPY apps/${SERVICE_NAME}/ /app/apps/${SERVICE_NAME}/

# Create logs directory
RUN mkdir -p /app/logs && chmod 777 /app/logs

EXPOSE 8000

# ----------------- Startup (Gunicorn + Uvicorn Worker) -----------------
# Assumes app instance is named `app` in apps/${SERVICE_NAME}/main.py
# Tune worker count (e.g., 4) based on your CPU
CMD ["sh", "-c", "gunicorn -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --log-level info main:app"]
# -----------------------------------------------------------------------
