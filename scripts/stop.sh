#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

load_env
secenv_compose down --remove-orphans || true

if [[ -f "$MLX_MANAGED_FILE" && -f "$MLX_PID_FILE" ]]; then
  pid="$(cat "$MLX_PID_FILE")"
  if [[ -n "$pid" ]] && ps -p "$pid" -o command= 2>/dev/null | grep -q mlx_lm.server; then
    kill "$pid" || true
  fi
  rm -f "$MLX_PID_FILE" "$MLX_MANAGED_FILE"
fi
