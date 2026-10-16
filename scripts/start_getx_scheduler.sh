#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a
[ -f "$ROOT/.env" ] && . "$ROOT/.env"
set +a
export PYTHONPATH="$ROOT"
export GETX_DIR="$ROOT/getx"
export GETX_QUEUE_DIR="${GETX_QUEUE_DIR:-$ROOT/runtime/getx_post_queue}"
export QUEUE_DIR="$GETX_QUEUE_DIR"
export GETX_PYTHON="${GETX_PYTHON:-/root/igmon/bin/python}"
exec "$GETX_PYTHON" "$ROOT/getx/scheduler.py" "$@"

