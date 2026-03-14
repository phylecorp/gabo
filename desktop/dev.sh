#!/usr/bin/env bash
# Start SAT Desktop in dev mode (FastAPI backend + Electron frontend)
set -e

NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
if [ "$NODE_MAJOR" -ge 25 ]; then
  echo "Error: Node $NODE_MAJOR is not supported. Use Node 20-24 LTS (see .nvmrc)."
  echo "  nvm install 22 && nvm use 22"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP="$ROOT/desktop"
API_PORT=8742

# Ensure venv exists and has api deps
if [ ! -f "$ROOT/venv/bin/python" ]; then
  echo "Creating Python venv..."
  python3 -m venv "$ROOT/venv"
fi
# Always ensure api extras are installed (handles added/changed deps)
"$ROOT/venv/bin/python" -c "import fastapi" 2>/dev/null || {
  echo "Installing Python dependencies..."
  "$ROOT/venv/bin/pip" install -e "$ROOT[api,all]" --quiet
}

# Ensure node_modules exist
if [ ! -d "$DESKTOP/node_modules" ]; then
  echo "Installing npm dependencies..."
  (cd "$DESKTOP" && npm install)
fi

# Start FastAPI backend
echo "Starting API server on port $API_PORT..."
"$ROOT/venv/bin/python" -m sat.api.main --port "$API_PORT" &
API_PID=$!

# Kill backend on exit
cleanup() {
  kill "$API_PID" 2>/dev/null
  wait "$API_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

# Wait for health check
for i in $(seq 1 30); do
  if curl -s "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1; then
    echo "API ready."
    break
  fi
  sleep 1
done

# Start Electron
echo "Launching Electron..."
(cd "$DESKTOP" && DEV_API_PORT="$API_PORT" npm run dev)
