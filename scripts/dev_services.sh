#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs/dev"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"

BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

if command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE_CMD=(docker-compose)
elif docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE_CMD=(docker compose)
else
  DOCKER_COMPOSE_CMD=()
fi

print_usage() {
  cat <<'EOF'
Usage:
  scripts/dev_services.sh start
  scripts/dev_services.sh stop
  scripts/dev_services.sh restart
  scripts/dev_services.sh status
  scripts/dev_services.sh logs [backend|frontend]

Environment overrides:
  BACKEND_HOST=0.0.0.0
  BACKEND_PORT=8000
  FRONTEND_HOST=0.0.0.0
  FRONTEND_PORT=3000
  DOCKER_COMPOSE_SUDO=1    # Use sudo for docker-compose commands
EOF
}

print_info() {
  echo "[INFO] $*"
}

print_warn() {
  echo "[WARN] $*"
}

print_error() {
  echo "[ERROR] $*" >&2
}

pid_is_running() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

get_pgid() {
  local pid="$1"
  ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]'
}

process_group_is_running() {
  local pgid="$1"
  kill -0 "-$pgid" >/dev/null 2>&1
}

read_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    cat "$pid_file"
  fi
}

cleanup_pid_file_if_stale() {
  local pid_file="$1"
  local pid
  pid="$(read_pid "$pid_file")"
  if [[ -n "${pid:-}" ]] && ! pid_is_running "$pid"; then
    rm -f "$pid_file"
  fi
}

detect_frontend_pid() {
  ps -eo pid=,args= | awk -v root="$ROOT_DIR/frontend" -v port="$FRONTEND_PORT" '
    index($0, root "/node_modules/.bin/vite") && index($0, "--port " port) { print $1; exit }
  '
}

detect_backend_pid() {
  ps -eo pid=,args= | awk -v root="$ROOT_DIR" -v port="$BACKEND_PORT" '
    index($0, root "/.venv/bin/python -m uvicorn app.main:app") && index($0, "--port " port) { print $1; exit }
  '
}

detect_pid_for_service() {
  local name="$1"
  case "$name" in
    Frontend)
      detect_frontend_pid
      ;;
    Backend)
      detect_backend_pid
      ;;
    *)
      return 1
      ;;
  esac
}

ensure_file_exists() {
  local path="$1"
  local hint="$2"
  if [[ ! -e "$path" ]]; then
    print_error "$path not found. $hint"
    exit 1
  fi
}

compose_cmd() {
  if [[ ${#DOCKER_COMPOSE_CMD[@]} -eq 0 ]]; then
    print_error "docker-compose is not available."
    exit 1
  fi

  if [[ "${DOCKER_COMPOSE_SUDO:-0}" == "1" ]]; then
    sudo "${DOCKER_COMPOSE_CMD[@]}" "$@"
  else
    "${DOCKER_COMPOSE_CMD[@]}" "$@"
  fi
}

start_backend() {
  cleanup_pid_file_if_stale "$BACKEND_PID_FILE"

  local pid
  pid="$(read_pid "$BACKEND_PID_FILE")"
  if [[ -n "${pid:-}" ]] && pid_is_running "$pid"; then
    print_info "Backend already running (PID: $pid)"
    return
  fi

  ensure_file_exists "$ROOT_DIR/.venv/bin/python" "Create the virtualenv first."
  ensure_file_exists "$ROOT_DIR/.env" "Copy .env.example to .env and adjust it."

  print_info "Starting backend on ${BACKEND_HOST}:${BACKEND_PORT}"
  (
    cd "$ROOT_DIR"
    nohup setsid env PYTHONPATH="$ROOT_DIR" \
      "$ROOT_DIR/.venv/bin/python" -m uvicorn app.main:app \
      --host "$BACKEND_HOST" \
      --port "$BACKEND_PORT" \
      --reload \
      >"$BACKEND_LOG_FILE" 2>&1 < /dev/null &
    echo $! >"$BACKEND_PID_FILE"
  )

  sleep 2
  pid="$(read_pid "$BACKEND_PID_FILE")"
  if [[ -n "${pid:-}" ]] && pid_is_running "$pid"; then
    print_info "Backend started (PID: $pid), log: $BACKEND_LOG_FILE"
  else
    print_error "Backend failed to start. Check $BACKEND_LOG_FILE"
    exit 1
  fi
}

start_frontend() {
  cleanup_pid_file_if_stale "$FRONTEND_PID_FILE"

  local pid
  pid="$(read_pid "$FRONTEND_PID_FILE")"
  if [[ -n "${pid:-}" ]] && pid_is_running "$pid"; then
    print_info "Frontend already running (PID: $pid)"
    return
  fi

  ensure_file_exists "$ROOT_DIR/frontend/package.json" "Frontend directory is missing."
  ensure_file_exists "$ROOT_DIR/frontend/node_modules" "Run npm install in frontend first."

  print_info "Starting frontend on ${FRONTEND_HOST}:${FRONTEND_PORT}"
  (
    cd "$ROOT_DIR/frontend"
    nohup setsid npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" \
      >"$FRONTEND_LOG_FILE" 2>&1 < /dev/null &
    echo $! >"$FRONTEND_PID_FILE"
  )

  sleep 2
  pid="$(read_pid "$FRONTEND_PID_FILE")"
  if [[ -n "${pid:-}" ]] && pid_is_running "$pid"; then
    print_info "Frontend started (PID: $pid), log: $FRONTEND_LOG_FILE"
  else
    print_error "Frontend failed to start. Check $FRONTEND_LOG_FILE"
    exit 1
  fi
}

start_datastores() {
  print_info "Starting MongoDB and Redis with docker-compose"
  if ! compose_cmd up -d mongodb redis; then
    print_error "Failed to start MongoDB/Redis."
    print_warn "If Docker needs privileges, rerun with DOCKER_COMPOSE_SUDO=1"
    exit 1
  fi
}

stop_process() {
  local name="$1"
  local pid_file="$2"
  local pid
  local pgid

  cleanup_pid_file_if_stale "$pid_file"
  pid="$(read_pid "$pid_file")"
  if [[ -z "${pid:-}" ]]; then
    pid="$(detect_pid_for_service "$name" || true)"
    if [[ -z "${pid:-}" ]]; then
      print_info "$name is not running"
      return
    fi
    print_warn "$name PID file missing, using detected PID: $pid"
  fi

  pgid="$(get_pgid "$pid")"

  if [[ -n "${pgid:-}" ]] && process_group_is_running "$pgid"; then
    print_info "Stopping $name process group (PGID: $pgid)"
    kill "-$pgid" >/dev/null 2>&1 || true
    for _ in {1..10}; do
      if ! process_group_is_running "$pgid"; then
        break
      fi
      sleep 1
    done
    if process_group_is_running "$pgid"; then
      print_warn "$name did not stop gracefully, forcing process group kill"
      kill -9 "-$pgid" >/dev/null 2>&1 || true
    fi
  elif pid_is_running "$pid"; then
    print_info "Stopping $name (PID: $pid)"
    kill "$pid" >/dev/null 2>&1 || true
  fi

  rm -f "$pid_file"
  print_info "$name stopped"
}

stop_datastores() {
  print_info "Stopping MongoDB and Redis"
  if ! compose_cmd stop mongodb redis; then
    print_warn "Failed to stop MongoDB/Redis with docker-compose"
  fi
}

show_process_status() {
  local name="$1"
  local pid_file="$2"
  local pid

  cleanup_pid_file_if_stale "$pid_file"
  pid="$(read_pid "$pid_file")"
  if [[ -n "${pid:-}" ]] && (process_group_is_running "$pid" || pid_is_running "$pid"); then
    echo "$name: running (PID: $pid)"
  else
    echo "$name: stopped"
  fi
}

show_datastore_status() {
  if [[ ${#DOCKER_COMPOSE_CMD[@]} -eq 0 ]]; then
    echo "datastores: docker-compose unavailable"
    return
  fi

  local output
  if output="$(compose_cmd ps mongodb redis 2>/dev/null)"; then
    echo "datastores:"
    echo "$output"
  else
    echo "datastores: unable to query status"
  fi
}

show_logs() {
  local target="${1:-}"
  case "$target" in
    backend)
      tail -f "$BACKEND_LOG_FILE"
      ;;
    frontend)
      tail -f "$FRONTEND_LOG_FILE"
      ;;
    "")
      print_info "Backend log: $BACKEND_LOG_FILE"
      print_info "Frontend log: $FRONTEND_LOG_FILE"
      ;;
    *)
      print_error "Unknown log target: $target"
      exit 1
      ;;
  esac
}

start_all() {
  start_datastores
  start_backend
  start_frontend
  print_info "All services started"
  print_info "Frontend: http://localhost:${FRONTEND_PORT}"
  print_info "Backend: http://localhost:${BACKEND_PORT}"
  print_info "API docs: http://localhost:${BACKEND_PORT}/docs"
}

stop_all() {
  stop_frontend_first=1
  if [[ "$stop_frontend_first" == "1" ]]; then
    stop_process "Frontend" "$FRONTEND_PID_FILE"
    stop_process "Backend" "$BACKEND_PID_FILE"
  else
    stop_process "Backend" "$BACKEND_PID_FILE"
    stop_process "Frontend" "$FRONTEND_PID_FILE"
  fi
  stop_datastores
  print_info "All services stopped"
}

restart_all() {
  stop_all
  start_all
}

status_all() {
  show_process_status "backend" "$BACKEND_PID_FILE"
  show_process_status "frontend" "$FRONTEND_PID_FILE"
  show_datastore_status
}

main() {
  local action="${1:-}"
  case "$action" in
    start)
      start_all
      ;;
    stop)
      stop_all
      ;;
    restart)
      restart_all
      ;;
    status)
      status_all
      ;;
    logs)
      show_logs "${2:-}"
      ;;
    *)
      print_usage
      exit 1
      ;;
  esac
}

main "$@"
