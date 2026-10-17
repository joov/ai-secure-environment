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

echo "==> mlx $MLX_MODEL on ${MLX_HOST}:${MLX_PORT}"
if ! curl -fsS "http://127.0.0.1:${MLX_PORT}/v1/models" >/dev/null 2>&1; then
  if [[ ! -x "$(command -v mlx_lm.server)" ]]; then
    echo "mlx_lm.server not found" >&2
    exit 1
  fi
  echo "==> start mlx_lm.server, log $PAPERCLIP_DIR/logs/mlx.log"
  nohup mlx_lm.server --model "$MLX_MODEL" --host "$MLX_HOST" --port "$MLX_PORT" \
    >"$PAPERCLIP_DIR/logs/mlx.log" 2>&1 &
  echo $! >"$MLX_PID_FILE"
  echo 1 >"$MLX_MANAGED_FILE"
  wait_http "http://127.0.0.1:${MLX_PORT}/v1/models" 180
else
  echo "==> mlx already up"
fi

echo "==> paperclip compose up"
paperclip_compose up -d --build
echo "==> wait operator"
wait_http "http://127.0.0.1:${OPERATOR_PORT}/health" 90
echo "==> wait secenv proxy"
wait_http "http://127.0.0.1:${SECENV_PROXY_PORT}/health" 180
echo "==> wait paperclip"
wait_http "http://127.0.0.1:${PAPERCLIP_PORT}/api/health" 90

echo "paperclip http://localhost:${PAPERCLIP_PORT}"
echo "secenv    http://127.0.0.1:${SECENV_PROXY_PORT}"
echo "mlx       http://127.0.0.1:${MLX_PORT}/v1"
