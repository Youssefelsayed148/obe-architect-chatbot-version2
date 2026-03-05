#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1}"

echo "Smoke test base URL: ${BASE_URL}"

echo "[1/4] health"
curl -fsS "${BASE_URL}/health" >/dev/null

echo "[2/4] widget.js"
curl -fsSI "${BASE_URL}/widget.js" >/dev/null

echo "[3/4] chat API via nginx /api prefix"
curl -fsS -X POST "${BASE_URL}/api/chat/message" \
  -H "Content-Type: application/json" \
  --data-raw '{"channel":"web","user_id":"smoke-user","session_id":null,"text":null,"button_id":null}' >/dev/null

echo "[4/4] RAG endpoint reachable (may return disabled detail)"
curl -fsS -X POST "${BASE_URL}/api/chat/ask" \
  -H "Content-Type: application/json" \
  --data-raw '{"question":"test"}' >/dev/null || true

echo "Smoke test finished."
