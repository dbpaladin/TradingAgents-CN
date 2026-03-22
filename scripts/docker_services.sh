#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE_CMD=(docker-compose)
elif docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE_CMD=(docker compose)
else
  DOCKER_COMPOSE_CMD=()
fi

print_info() {
  echo "[INFO] $*"
}

print_error() {
  echo "[ERROR] $*" >&2
}

compose_cmd() {
  if [[ ${#DOCKER_COMPOSE_CMD[@]} -eq 0 ]]; then
    print_error "docker-compose is not available"
    exit 1
  fi

  cd "$ROOT_DIR"
  local output status
  if [[ "${DOCKER_COMPOSE_SUDO:-0}" == "1" ]]; then
    set +e
    output="$(sudo "${DOCKER_COMPOSE_CMD[@]}" "$@" 2>&1)"
    status=$?
    set -e
  else
    set +e
    output="$("${DOCKER_COMPOSE_CMD[@]}" "$@" 2>&1)"
    status=$?
    set -e
  fi

  if [[ $status -ne 0 ]]; then
    print_error "Docker command failed"
    echo "$output" >&2
    if [[ "${DOCKER_COMPOSE_SUDO:-0}" != "1" ]] && grep -qiE "permission denied|got permission denied" <<<"$output"; then
      print_error "Try again with: DOCKER_COMPOSE_SUDO=1 ./scripts/docker_services.sh $*"
    fi
    exit $status
  fi

  [[ -n "$output" ]] && echo "$output"
}

case "${1:-}" in
  start)
    print_info "Starting Docker services: mongodb, redis"
    compose_cmd up -d mongodb redis
    ;;
  stop)
    print_info "Stopping Docker services: mongodb, redis"
    compose_cmd stop mongodb redis
    ;;
  restart)
    print_info "Restarting Docker services: mongodb, redis"
    compose_cmd stop mongodb redis
    compose_cmd up -d mongodb redis
    ;;
  status)
    compose_cmd ps mongodb redis
    ;;
  logs)
    compose_cmd logs -f mongodb redis
    ;;
  *)
    cat <<'EOF'
Usage: scripts/docker_services.sh {start|stop|restart|status|logs}

This script manages Docker services only:
  - mongodb
  - redis
EOF
    exit 1
    ;;
esac
