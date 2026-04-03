#!/usr/bin/env bash

set -euo pipefail

check_python() {
  if ! command -v python >/dev/null 2>&1; then
    echo "Python 3.9+ is required but was not found."
    exit 1
  fi

  if ! python - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit(1)
PY
  then
    echo "Python 3.9+ is required. Current version: $(python --version 2>&1)"
    exit 1
  fi
}

check_node() {
  if ! command -v node >/dev/null 2>&1; then
    echo "Node.js 16+ is required but was not found."
    exit 1
  fi

  local node_major
  node_major=$(node -p "process.versions.node.split('.')[0]")
  if [ "${node_major}" -lt 16 ]; then
    echo "Node.js 16+ is required. Current version: $(node --version)"
    exit 1
  fi
}

check_dataset() {
  if [ ! -f "training/microbiology_cultures_demographics.csv" ]; then
    cat <<'EOF'
Missing training/microbiology_cultures_demographics.csv.
Download the Dryad dataset used by this project and place the file in training/ before starting the app.
EOF
    exit 1
  fi
}

ensure_model() {
  if [ ! -f "backend/model/antibiotic_model.pkl" ]; then
    echo "Model not found. Training a new model first..."
    python training/train.py
  fi
}

start_backend() {
  (cd backend && uvicorn app.main:app --port 8000) &
  BACKEND_PID=$!
}

main() {
  check_python
  check_node
  check_dataset
  ensure_model
  start_backend

  echo "✅ App running at http://localhost:3000 | API at http://localhost:8000/docs"
  (cd frontend && npm run dev)
}

trap 'if [ -n "${BACKEND_PID:-}" ]; then kill "${BACKEND_PID}" >/dev/null 2>&1 || true; fi' EXIT

main