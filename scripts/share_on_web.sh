#!/usr/bin/env bash
# Public tunnel via ngrok to the Vite dev server; tunnel stops when you exit this script.
# One-time setup: https://dashboard.ngrok.com/get-started/setup — then:
#   ngrok config add-authtoken YOUR_TOKEN
# Run backend + web first (--host 0.0.0.0 same as LAN). Port configurable with FMR_TUNNEL_PORT.

set -euo pipefail

PORT="${FMR_TUNNEL_PORT:-5173}"
NGROK_PID=""

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "${NGROK_PID}" ]] && kill -0 "${NGROK_PID}" 2>/dev/null; then
    echo ""
    echo "Stopping ngrok (pid ${NGROK_PID})…"
    kill "${NGROK_PID}" 2>/dev/null || true
    wait "${NGROK_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok not found. Install from https://ngrok.com/download and ensure it is on PATH." >&2
  exit 1
fi

if ! curl -fsS --connect-timeout 1 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
  echo "Note: nothing replied on http://127.0.0.1:${PORT} yet." >&2
  echo "      Start first: npm run dev -- --host 0.0.0.0 --port ${PORT}" >&2
  echo ""
fi

echo "Starting ngrok tunnel → http://127.0.0.1:${PORT}"
ngrok http "http://127.0.0.1:${PORT}" --log=stderr >/tmp/ngrok-fmr-share.log 2>&1 &
NGROK_PID=$!

parse_public_https() {
  curl -fsS "${1:-http://127.0.0.1:4040/api/tunnels}" 2>/dev/null | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(2)
for t in d.get("tunnels") or []:
    u = t.get("public_url") or ""
    if u.startswith("https:"):
        print(u)
        raise SystemExit(0)
raise SystemExit(1)
'
}

PUBLIC_URL=""
for _ in $(seq 1 150); do
  if PUBLIC_URL="$(parse_public_https 2>/dev/null || true)" && [[ -n "${PUBLIC_URL}" ]]; then
    break
  fi
  sleep 0.15
done

if [[ -z "${PUBLIC_URL}" ]]; then
  echo ""
  echo "Could not obtain public URL from ngrok (timeout or error)." >&2
  echo "Log: /tmp/ngrok-fmr-share.log" >&2
  tail -n 30 /tmp/ngrok-fmr-share.log >&2 || true
  exit 1
fi

echo ""
echo "Share this URL (HTTPS):"
echo "  ${PUBLIC_URL}"
echo ""
echo "This host must be running:"
echo "  backend: uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo "  web:     npm run dev -- --host 0.0.0.0 --port ${PORT}"
echo ""
echo "While this script runs, the dev app is reachable on the Internet at that URL."
echo "Stop with Enter or Ctrl+C — ngrok shuts down."
echo ""

read -r _
