#!/usr/bin/env bash
set -Eeuo pipefail

ENTRYPOINT_DIR="${ENTRYPOINT_DIR:-/docker-entrypoint.d}"

run_parts() {
  local dir="$1"

  [[ -d "$dir" ]] || return 0

  echo "[entrypoint] loading scripts from: $dir"

  local file
  for file in "$dir"/*; do
    [[ -e "$file" ]] || continue

    case "$file" in
      *.sh)
        if [[ -x "$file" ]]; then
          echo "[entrypoint] running: $file"
          "$file"
        else
          echo "[entrypoint] sourcing: $file"
          # shellcheck disable=SC1090
          . "$file"
        fi
        ;;
      *)
        echo "[entrypoint] skipping: $file"
        ;;
    esac
  done
}

run_parts "$ENTRYPOINT_DIR"

echo "[entrypoint] starting main process: $*"
exec "$@"