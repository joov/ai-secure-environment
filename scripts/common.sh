#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECENV_DIR="$ROOT/secenv"
MLX_PID_FILE="$SECENV_DIR/logs/mlx.pid"
MLX_MANAGED_FILE="$SECENV_DIR/logs/mlx.managed"

load_env() {
  python3 - "$SECENV_DIR/.env" "$ROOT" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
root = sys.argv[2]
lines = path.read_text().splitlines() if path.exists() else []
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
  source "$SECENV_DIR/.env"
  set +a
  export HOST_ROOT="$ROOT"
}

ensure_dirs() {
  mkdir -p \
    "$SECENV_DIR/logs" \
    "$SECENV_DIR/data" \
    "$SECENV_DIR/secrets/agent-a" \
    "$SECENV_DIR/secrets/agent-b" \
    "$SECENV_DIR/workspace" \
    "$SECENV_DIR/policies"
  chmod 1777 "$SECENV_DIR/logs" "$SECENV_DIR/data" "$SECENV_DIR/secrets" "$SECENV_DIR/workspace"
  if [[ ! -f "$SECENV_DIR/workspace/notes.txt" ]]; then
    printf 'hello from workspace\n' >"$SECENV_DIR/workspace/notes.txt"
  fi
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
