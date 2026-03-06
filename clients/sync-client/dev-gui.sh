#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/packages/gui"

cleanup() {
    if [ -n "$VITE_PID" ]; then
        kill "$VITE_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

echo "Starting Vite dev server..."
npm run dev &
VITE_PID=$!

# Wait for Vite to be ready
sleep 3

echo "Launching Electron..."
npm start
