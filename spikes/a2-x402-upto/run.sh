#!/usr/bin/env bash
# A2 spike runner (inside the dev image). Starts the upto server, runs the client.
set -uo pipefail

pip install -q --break-system-packages flask

python3 server.py > server.log 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 30); do
  curl -s -o /dev/null http://127.0.0.1:8000/report && break || sleep 1
done

python3 client.py
