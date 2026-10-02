#!/usr/bin/env bash
# P2 运维：统一启动入口。取代裸 uvicorn，固化端口/日志级别/输出目标/前台运行。
# 用法：./run.sh [port]  默认 8001；不占用 8000（旧服务）与 80（未批准）。
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-8001}"
export OPTV2_LOG_LEVEL="${OPTV2_LOG_LEVEL:-INFO}"
# 默认 stderr（便于 systemd/journal 采集）；生产可设 OPTV2_LOG_TARGET=file:/root/option-platform-v2/backend/app.log
export OPTV2_LOG_TARGET="${OPTV2_LOG_TARGET:-stderr}"
export PYTHONUNBUFFERED=1

echo "[run.sh] starting option-platform-v2 on :${PORT} (log=${OPTV2_LOG_TARGET}/${OPTV2_LOG_LEVEL})"
exec /usr/bin/python3.11 -m uvicorn main:app --host 0.0.0.0 --port "${PORT}" --no-proxy-headers
