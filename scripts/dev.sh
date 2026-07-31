#!/usr/bin/env bash
# Dev server launcher. Ports are FIXED, do not change:
#   backend 8002, frontend 5175
# — 5173/8000/8001/23456 are already used by other projects on this machine
# (my-academy/my-news/exchange-fee/my-youtube).
#
# Usage: bash scripts/dev.sh [backend|frontend]   (no arg = both)
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_backend() {
  cd "$repo_root/backend"
  source .venv/bin/activate
  exec uvicorn app.main:app --port 8002 --reload
}

run_frontend() {
  cd "$repo_root/frontend"
  exec npx vite --port 5175 --strictPort
}

case "${1:-both}" in
  backend)
    run_backend
    ;;
  frontend)
    run_frontend
    ;;
  both)
    ( run_backend ) &
    backend_pid=$!
    ( run_frontend ) &
    frontend_pid=$!
    trap 'kill "$backend_pid" "$frontend_pid" 2>/dev/null' EXIT
    wait
    ;;
  *)
    echo "usage: bash scripts/dev.sh [backend|frontend]" >&2
    exit 1
    ;;
esac
