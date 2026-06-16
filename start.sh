#!/usr/bin/env bash
# KINGDOM PRIME — one-click start (macOS / Linux)
set -e
cd "$(dirname "$0")"

PY=venv/bin/python
if [ ! -x "$PY" ]; then
  echo "[1/3] Setting up environment (first time only)..."
  PYBIN=$(command -v python3.12 || command -v python3)
  "$PYBIN" -m venv venv
  "$PY" -m pip install --quiet --no-index --find-links=wheels -r requirements.txt 2>/dev/null \
    || "$PY" -m pip install --quiet -r requirements.txt
  echo "      Done."
fi

echo "[2/3] Starting Kingdom Prime server on http://localhost:8000 ..."
export PYTHONPATH="$PWD/src"
echo "[setup] API key setup..."
"$PY" scripts/setup_env.py
"$PY" -m uvicorn main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!

echo "[3/3] Opening dashboard..."
sleep 3
( command -v open >/dev/null && open "http://localhost:8000/" ) \
  || ( command -v xdg-open >/dev/null && xdg-open "http://localhost:8000/" ) || true

echo "Ready!  Dashboard: http://localhost:8000/"
echo "Press Ctrl+C to stop."
trap "kill $SERVER_PID 2>/dev/null" EXIT
wait $SERVER_PID
