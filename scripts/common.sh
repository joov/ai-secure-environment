#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAPERCLIP_DIR="$ROOT/paperclip"
SECENV_DIR="$ROOT/secenv"
MLX_PID_FILE="$PAPERCLIP_DIR/logs/mlx.pid"
MLX_MANAGED_FILE="$PAPERCLIP_DIR/logs/mlx.managed"

load_env() {
  python3 - "$PAPERCLIP_DIR/.env" "$SECENV_DIR/.env" "$ROOT" <<'PY'
from pathlib import Path
import sys
files = [Path(sys.argv[1]), Path(sys.argv[2])]
root = sys.argv[3]
for path in files:
    lines = path.read_text().splitlines()
    found = False
    out = []
    for line in lines:
        if line.startswith("HOST_ROOT="):
            out.append(f'HOST_ROOT="{root}"')
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f'HOST_ROOT="{root}"')
    path.write_text("\n".join(out) + "\n")
PY
  set -a
  # shellcheck disable=SC1091
  source "$PAPERCLIP_DIR/.env"
  # shellcheck disable=SC1091
  source "$SECENV_DIR/.env"
  set +a
  export HOST_ROOT="$ROOT"
}

ensure_dirs() {
  mkdir -p \
    "$PAPERCLIP_DIR/data/paperclip" \
    "$PAPERCLIP_DIR/data/postgres" \
    "$PAPERCLIP_DIR/logs" \
    "$PAPERCLIP_DIR/config" \
    "$SECENV_DIR/logs" \
    "$SECENV_DIR/workspace" \
    "$SECENV_DIR/config" \
    "$SECENV_DIR/iac" \
    "$SECENV_DIR/data"
  chmod 1777 "$PAPERCLIP_DIR/logs" "$SECENV_DIR/logs" "$SECENV_DIR/workspace"
}

paperclip_compose() {
  docker compose --project-name paperclip --env-file "$PAPERCLIP_DIR/.env" -f "$PAPERCLIP_DIR/docker-compose.yml" "$@"
}

secenv_compose() {
  docker compose --project-name secenv --env-file "$SECENV_DIR/.env" -f "$SECENV_DIR/docker-compose.yml" "$@"
}

wait_http() {
  local url="$1" tries="${2:-60}"
  local i
  for ((i = 1; i <= tries; i++)); do
    echo "wait $i/$tries $url"
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "up $url"
      return 0
    fi
    sleep 2
  done
  echo "timeout waiting for $url" >&2
  return 1
}
