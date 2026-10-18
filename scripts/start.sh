#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

echo "==> load env"
load_env
echo "==> ensure dirs"
ensure_dirs

echo "==> docker info"
if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running" >&2
  exit 1
fi

MLX_HOST="${MLX_HOST:-127.0.0.1}"
echo "==> mlx $MLX_MODEL on ${MLX_HOST}:${MLX_PORT}"
if ! curl -fsS "http://127.0.0.1:${MLX_PORT}/v1/models" >/dev/null 2>&1; then
  if [[ ! -x "$(command -v mlx_lm.server)" ]]; then
    echo "mlx_lm.server not found" >&2
    exit 1
  fi
  echo "==> start mlx_lm.server, log $SECENV_DIR/logs/mlx.log"
  nohup mlx_lm.server --model "$MLX_MODEL" --host "$MLX_HOST" --port "$MLX_PORT" \
    >"$SECENV_DIR/logs/mlx.log" 2>&1 &
  echo $! >"$MLX_PID_FILE"
  echo 1 >"$MLX_MANAGED_FILE"
  wait_http "http://127.0.0.1:${MLX_PORT}/v1/models" 180
else
  echo "==> mlx already up"
fi

echo "==> secenv compose up"
secenv_compose up -d --build --remove-orphans
echo "==> wait broker"
wait_http "http://127.0.0.1:${BROKER_PORT}/health" 90
echo "==> wait hitl"
wait_http "http://127.0.0.1:${HITL_PORT}/health" 30
echo "==> wait ledger"
wait_http "http://127.0.0.1:${LEDGER_PORT}/health" 30

echo "broker http://127.0.0.1:${BROKER_PORT}"
echo "hitl   http://127.0.0.1:${HITL_PORT}"
echo "ledger http://127.0.0.1:${LEDGER_PORT}"
echo "mlx    http://127.0.0.1:${MLX_PORT}/v1"
