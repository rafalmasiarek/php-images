#!/usr/bin/env bash
set -Eeuo pipefail

ENTRYPOINT_DIR="${ENTRYPOINT_DIR:-/docker-entrypoint.d}"
ENTRYPOINT_DEBUG="${ENTRYPOINT_DEBUG:-0}"
ENTRYPOINT_DEBUG_FD="${ENTRYPOINT_DEBUG_FD:-2}"

case "$ENTRYPOINT_DEBUG_FD" in
  1|2) ;;
  *)
    echo "Invalid ENTRYPOINT_DEBUG_FD=$ENTRYPOINT_DEBUG_FD, expected 1 or 2" >&2
    exit 1
    ;;
esac

log() {
  [[ "$ENTRYPOINT_DEBUG" == "1" ]] || return 0
  printf '[entrypoint] %s\n' "$*" >&"$ENTRYPOINT_DEBUG_FD"
}

run_parts() {
  local dir="$1"

  [[ -d "$dir" ]] || return 0

  log "loading scripts from: $dir"

  local file
  for file in "$dir"/*; do
    [[ -e "$file" ]] || continue

    case "$file" in
      *.sh)
        if [[ -x "$file" ]]; then
          log "running: $file"
          "$file"
        else
          log "sourcing: $file"
          # shellcheck disable=SC1090
          . "$file"
        fi
        ;;
      *)
        log "skipping: $file"
        ;;
    esac
  done
}

run_parts "$ENTRYPOINT_DIR"

log "starting main process: $*"
exec "$@"
