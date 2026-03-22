#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT_DIR}/.run"
LOG_DIR="${ROOT_DIR}/logs"
FRONTEND_PID_FILE="${RUN_DIR}/frontend.pid"
FRONTEND_LOG_FILE="${LOG_DIR}/frontend-service.out"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

print_info() {
  echo "[INFO] $*"
}

print_warn() {
  echo "[WARN] $*"
}

print_error() {
  echo "[ERROR] $*" >&2
}

read_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    tr -d '[:space:]' < "$pid_file"
  fi
}

pid_is_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

get_pgid() {
  local pid="${1:-}"
  ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]'
}

cleanup_stale_pid() {
  local pid_file="$1"
  local pid
  pid="$(read_pid "$pid_file")"
  if [[ -n "${pid:-}" ]] && ! pid_is_running "$pid"; then
    rm -f "$pid_file"
  fi
}

start_frontend() {
  cleanup_stale_pid "$FRONTEND_PID_FILE"

  local pid
  pid="$(read_pid "$FRONTEND_PID_FILE")"
  if pid_is_running "${pid:-}"; then
    print_info "Frontend already running (PID: $pid)"
    return 0
  fi

  [[ -f "${ROOT_DIR}/frontend/package.json" ]] || { print_error "frontend/package.json not found"; exit 1; }
  [[ -d "${ROOT_DIR}/frontend/node_modules" ]] || { print_error "frontend/node_modules not found. Run npm install first."; exit 1; }

  print_info "Starting frontend on ${FRONTEND_HOST}:${FRONTEND_PORT}"
  (
    cd "${ROOT_DIR}/frontend"
    nohup setsid npm run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}" >"${FRONTEND_LOG_FILE}" 2>&1 < /dev/null &
    echo $! > "${FRONTEND_PID_FILE}"
  )

  sleep 2
  pid="$(read_pid "$FRONTEND_PID_FILE")"
  if ! pid_is_running "${pid:-}"; then
    print_error "Frontend failed to start. Check ${FRONTEND_LOG_FILE}"
    exit 1
  fi

  print_info "Frontend started (PID: $pid)"
  print_info "Log file: ${FRONTEND_LOG_FILE}"
}

stop_frontend() {
  cleanup_stale_pid "$FRONTEND_PID_FILE"

  local pid pgid
  pid="$(read_pid "$FRONTEND_PID_FILE")"
  if [[ -z "${pid:-}" ]]; then
    print_info "Frontend is not running"
    return 0
  fi

  pgid="$(get_pgid "$pid")"
  if [[ -n "${pgid:-}" ]]; then
    print_info "Stopping frontend process group (PGID: $pgid)"
    kill "-$pgid" >/dev/null 2>&1 || true
  else
    print_info "Stopping frontend process (PID: $pid)"
    kill "$pid" >/dev/null 2>&1 || true
  fi

  for _ in {1..10}; do
    if ! pid_is_running "$pid"; then
      rm -f "$FRONTEND_PID_FILE"
      print_info "Frontend stopped"
      return 0
    fi
    sleep 1
  done

  print_warn "Frontend did not stop gracefully, forcing kill"
  if [[ -n "${pgid:-}" ]]; then
    kill -9 "-$pgid" >/dev/null 2>&1 || true
  else
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$FRONTEND_PID_FILE"
  print_info "Frontend stopped"
}

status_frontend() {
  cleanup_stale_pid "$FRONTEND_PID_FILE"

  local pid
  pid="$(read_pid "$FRONTEND_PID_FILE")"
  if pid_is_running "${pid:-}"; then
    print_info "Frontend is running (PID: $pid)"
  else
    print_info "Frontend is stopped"
  fi
}

start_all() {
  "${ROOT_DIR}/scripts/backend_service.sh" start
  start_frontend
  print_info "App services started"
  print_info "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
  print_info "Backend: http://127.0.0.1:8000"
}

stop_all() {
  stop_frontend
  "${ROOT_DIR}/scripts/backend_service.sh" stop
  print_info "App services stopped"
}

restart_all() {
  stop_all
  start_all
}

status_all() {
  "${ROOT_DIR}/scripts/backend_service.sh" status
  status_frontend
}

show_logs() {
  case "${1:-}" in
    backend)
      "${ROOT_DIR}/scripts/backend_service.sh" logs
      ;;
    frontend)
      mkdir -p "$LOG_DIR"
      touch "$FRONTEND_LOG_FILE"
      tail -f "$FRONTEND_LOG_FILE"
      ;;
    "")
      print_info "Backend log: ${ROOT_DIR}/logs/backend-service.out"
      print_info "Frontend log: ${FRONTEND_LOG_FILE}"
      ;;
    *)
      print_error "Unknown log target: $1"
      exit 1
      ;;
  esac
}

case "${1:-}" in
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
    cat <<'EOF'
Usage: scripts/app_services.sh {start|stop|restart|status|logs [backend|frontend]}

This script manages:
  - FastAPI backend
  - Vite frontend
EOF
    exit 1
    ;;
esac
