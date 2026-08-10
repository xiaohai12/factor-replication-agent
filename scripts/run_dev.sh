#!/usr/bin/env bash
# Starts the backend (uvicorn) and frontend (vite) dev servers together.
# Usage:
#   scripts/run_dev.sh            # writes to the real runs/ dir
#   scripts/run_dev.sh --scratch  # writes to .runs_scratch/ instead (safe to wipe)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "${1:-}" == "--scratch" ]]; then
  export FACTOR_AGENT_RUNS_DIR=.runs_scratch
  echo "FACTOR_AGENT_RUNS_DIR=.runs_scratch (test/scratch mode -- safe to rm -rf .runs_scratch afterward)"
else
  unset FACTOR_AGENT_RUNS_DIR || true
  echo "Writing to the real runs/ directory."
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# Free the ports if a stale process is still holding them from a previous run.
for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  pid="$(lsof -ti:"$port" 2>/dev/null || true)"
  if [[ -n "$pid" ]]; then
    echo "Port $port is in use by PID $pid -- killing it first."
    kill -9 $pid 2>/dev/null || true
  fi
done

PIDS=()
cleanup() {
  echo "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "Starting backend on http://127.0.0.1:$BACKEND_PORT ..."
.venv/bin/python3 -m uvicorn backend.main:app --port "$BACKEND_PORT" &
PIDS+=($!)

echo "Starting frontend on http://localhost:$FRONTEND_PORT ..."
(cd frontend && npm run dev -- --port "$FRONTEND_PORT") &
PIDS+=($!)

wait
