#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${ROOT_DIR}/logs/backend.pid"
LOG_FILE="${ROOT_DIR}/logs/backend-service.out"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_RELOAD="${BACKEND_RELOAD:-0}"

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
  if [[ -f "$PID_FILE" ]]; then
    tr -d '[:space:]' < "$PID_FILE"
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
  local pid
  pid="$(read_pid)"
  if [[ -n "${pid:-}" ]] && ! pid_is_running "$pid"; then
    rm -f "$PID_FILE"
  fi
}

start_backend() {
  cleanup_stale_pid

  local pid
  pid="$(read_pid)"
  if pid_is_running "${pid:-}"; then
    print_info "Backend already running (PID: $pid)"
    return 0
  fi

  [[ -x "$PYTHON_BIN" ]] || { print_error "Python virtualenv not found: $PYTHON_BIN"; exit 1; }
  [[ -f "${ROOT_DIR}/.env" ]] || { print_error ".env not found in project root"; exit 1; }

  mkdir -p "${ROOT_DIR}/logs"

  local -a cmd=("$PYTHON_BIN" -m app)
  if [[ "$BACKEND_RELOAD" == "1" ]]; then
    cmd=("$PYTHON_BIN" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload)
  fi

  print_info "Starting backend on ${BACKEND_HOST}:${BACKEND_PORT}"
  (
    cd "$ROOT_DIR"
    nohup setsid env PYTHONPATH="$ROOT_DIR" "${cmd[@]}" >"$LOG_FILE" 2>&1 < /dev/null &
    echo $! > "$PID_FILE"
  )

  sleep 2
  pid="$(read_pid)"
  if ! pid_is_running "${pid:-}"; then
    print_error "Backend failed to start. Check $LOG_FILE"
    exit 1
  fi

  for _ in {1..20}; do
    if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
      print_info "Backend started (PID: $pid)"
      print_info "Health check OK: http://127.0.0.1:${BACKEND_PORT}/api/health"
      print_info "Log file: $LOG_FILE"
      return 0
    fi
    sleep 1
  done

  print_warn "Process started but health check did not pass yet. Check $LOG_FILE"
}

stop_backend() {
  cleanup_stale_pid

  local pid pgid
  pid="$(read_pid)"
  if [[ -z "${pid:-}" ]]; then
    print_info "Backend is not running"
    return 0
  fi

  pgid="$(get_pgid "$pid")"
  if [[ -n "${pgid:-}" ]]; then
    print_info "Stopping backend process group (PGID: $pgid)"
    kill "-$pgid" >/dev/null 2>&1 || true
  else
    print_info "Stopping backend process (PID: $pid)"
    kill "$pid" >/dev/null 2>&1 || true
  fi

  for _ in {1..10}; do
    if ! pid_is_running "$pid"; then
      rm -f "$PID_FILE"
      print_info "Backend stopped"
      return 0
    fi
    sleep 1
  done

  print_warn "Backend did not stop gracefully, forcing kill"
  if [[ -n "${pgid:-}" ]]; then
    kill -9 "-$pgid" >/dev/null 2>&1 || true
  else
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$PID_FILE"
  print_info "Backend stopped"
}

status_backend() {
  cleanup_stale_pid

  local pid
  pid="$(read_pid)"
  if pid_is_running "${pid:-}"; then
    print_info "Backend is running (PID: $pid)"
    if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
      print_info "Health check OK"
    else
      print_warn "Process exists, but health check failed"
    fi
  else
    print_info "Backend is stopped"
  fi
}

show_logs() {
  mkdir -p "${ROOT_DIR}/logs"
  touch "$LOG_FILE"
  tail -f "$LOG_FILE"
}

case "${1:-}" in
  start)
    start_backend
    ;;
  stop)
    stop_backend
    ;;
  restart)
    stop_backend
    start_backend
    ;;
  status)
    status_backend
    ;;
  logs)
    show_logs
    ;;
  *)
    cat <<'EOF'
Usage: scripts/backend_service.sh {start|stop|restart|status|logs}

Environment variables:
  BACKEND_PORT=8000
  BACKEND_HOST=0.0.0.0
  BACKEND_RELOAD=0
EOF
    exit 1
    ;;
esac
