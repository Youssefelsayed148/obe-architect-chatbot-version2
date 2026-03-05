#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env.production}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

required_vars=(
  POSTGRES_DSN
  REDIS_URL
  ADMIN_API_KEY
  SENDGRID_API_KEY
  EMAIL_FROM
  LEADS_NOTIFY_TO
)

missing=()
for var in "${required_vars[@]}"; do
  if ! grep -E "^\s*${var}=" "$ENV_FILE" >/dev/null; then
    missing+=("$var")
  fi
done

wa_any=false
if grep -E "^\s*WHATSAPP_VERIFY_TOKEN=" "$ENV_FILE" >/dev/null; then wa_any=true; fi
if grep -E "^\s*WHATSAPP_ACCESS_TOKEN=" "$ENV_FILE" >/dev/null; then wa_any=true; fi
if grep -E "^\s*WHATSAPP_PHONE_NUMBER_ID=" "$ENV_FILE" >/dev/null; then wa_any=true; fi

if [[ "$wa_any" == "true" ]]; then
  wa_vars=(WHATSAPP_VERIFY_TOKEN WHATSAPP_ACCESS_TOKEN WHATSAPP_PHONE_NUMBER_ID)
  for var in "${wa_vars[@]}"; do
    if ! grep -E "^\s*${var}=" "$ENV_FILE" >/dev/null; then
      missing+=("$var")
    fi
  done
fi

if (( ${#missing[@]} > 0 )); then
  echo "Missing required vars in $ENV_FILE: ${missing[*]}" >&2
  exit 1
fi

echo "Env check OK for $ENV_FILE"
