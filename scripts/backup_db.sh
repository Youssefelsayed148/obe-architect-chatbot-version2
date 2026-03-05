#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TS="$(date +%Y%m%d_%H%M%S)"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

set -a
source "$ENV_FILE"
set +a

DB_NAME="${POSTGRES_DB:-obe_bot}"
DB_USER="${POSTGRES_USER:-obe_user}"
OUT_FILE="${BACKUP_DIR}/db_${DB_NAME}_${TS}.sql.gz"

echo "Creating backup: ${OUT_FILE}"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$OUT_FILE"

echo "Backup completed: ${OUT_FILE}"
