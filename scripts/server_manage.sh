#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"
LOG_DIR="${PROJECT_DIR}/logs/api"
PID_FILE="${PROJECT_DIR}/.uvicorn.pid"
PORT="${PORT:-8000}"

usage() {
  cat <<'EOF'
Usage:
  server_manage.sh setup      # 创建虚拟环境并安装依赖（首次执行）
  server_manage.sh start      # 以后台方式启动 uvicorn
  server_manage.sh stop       # 停止后台 uvicorn
  server_manage.sh status     # 查看 uvicorn 运行状态
EOF
}

require_venv() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[ERROR] 虚拟环境不存在，请先执行: server_manage.sh setup"
    exit 1
  fi
  # shellcheck source=/dev/null
  source "${VENV_DIR}/bin/activate"
}

case "${1:-}" in
  setup)
    python3 -m venv "${VENV_DIR}"
    # shellcheck source=/dev/null
    source "${VENV_DIR}/bin/activate"
    pip install --upgrade pip
    pip install -r "${PROJECT_DIR}/requirements_api.txt"
    playwright install chromium
    echo "[INFO] 依赖安装完成。"
    ;;

  start)
    require_venv
    mkdir -p "${LOG_DIR}"
    if [[ -f "${PID_FILE}" ]] && ps -p "$(cat "${PID_FILE}")" > /dev/null 2>&1; then
      echo "[INFO] uvicorn 已在运行 (PID $(cat "${PID_FILE}"))"
      exit 0
    fi
    export UVICORN_NO_UVLOOP=1
    nohup uvicorn main:app --host 0.0.0.0 --port "${PORT}" --loop asyncio \
      > "${LOG_DIR}/server.log" 2>&1 &
    echo $! > "${PID_FILE}"
    echo "[INFO] uvicorn 已启动 (PID $(cat "${PID_FILE}"))，日志输出: ${LOG_DIR}/server.log"
    ;;

  stop)
    if [[ -f "${PID_FILE}" ]]; then
      PID="$(cat "${PID_FILE}")"
      if ps -p "${PID}" > /dev/null 2>&1; then
        kill "${PID}"
        echo "[INFO] 已停止 uvicorn (PID ${PID})"
      fi
      rm -f "${PID_FILE}"
    else
      echo "[INFO] 未发现运行中的 uvicorn"
    fi
    ;;

  status)
    if [[ -f "${PID_FILE}" ]] && ps -p "$(cat "${PID_FILE}")" > /dev/null 2>&1; then
      echo "[INFO] uvicorn 正在运行 (PID $(cat "${PID_FILE}"))"
      exit 0
    fi
    echo "[INFO] uvicorn 未运行"
    exit 1
    ;;

  *)
    usage
    exit 1
    ;;
esac
