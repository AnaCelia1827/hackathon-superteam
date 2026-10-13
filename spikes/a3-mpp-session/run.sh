#!/usr/bin/env bash
# A3 spike runner (inside the dev image). Starts the session server, runs the client.
set -uo pipefail

python3 server.py > server.log 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 30); do
  curl -s -o /dev/null http://127.0.0.1:8001/session && break || sleep 1
done

python3 client.py
