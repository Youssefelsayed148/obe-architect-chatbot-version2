#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"

cd "$PROJECT_DIR"

echo "[1/5] Updating source"
git pull --ff-only

echo "[2/5] Building containers"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build

echo "[3/5] Starting services"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d

echo "[4/5] Current service state"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps

echo "[5/5] Health probes"
curl -fsS http://127.0.0.1/health && echo
curl -fsSI http://127.0.0.1/widget.js | sed -n '1,8p'

echo "Recent nginx/app logs:"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=80 nginx app
