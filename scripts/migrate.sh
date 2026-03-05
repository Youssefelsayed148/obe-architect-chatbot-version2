#!/usr/bin/env bash
set -euo pipefail

if command -v alembic >/dev/null 2>&1 && [ -f "alembic.ini" ]; then
  echo "Running Alembic upgrade head..."
  alembic upgrade head
  exit 0
fi

echo "Alembic is not configured in this repository. Skipping alembic migrations."
