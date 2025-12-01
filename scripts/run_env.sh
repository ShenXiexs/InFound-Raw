#!/usr/bin/env bash
#
# run_env.sh ENV_FILE PORT
# 快速在指定端口启动一份服务，并加载对应的 .env 文件。

set -euo pipefail

ENV_FILE=${1:-.env}
SERVICE_PORT=${2:-8000}

if [ ! -f "$ENV_FILE" ]; then
  echo "Env file $ENV_FILE not found."
  exit 1
fi

echo "[run_env] Using env file: $ENV_FILE"
echo "[run_env] Listening on port: $SERVICE_PORT"

exec uvicorn main:app \
  --host 0.0.0.0 \
  --port "$SERVICE_PORT" \
  --env-file "$ENV_FILE"
