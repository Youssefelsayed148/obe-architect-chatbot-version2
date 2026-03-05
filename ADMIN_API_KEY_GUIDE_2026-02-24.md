# OBE Bot Admin API Key Guide

Date: 2026-02-24  
Project: `obe-architects-bot`

## 1) What the Admin API Key Is

`ADMIN_API_KEY` is a shared secret sent in the HTTP header:

`X-API-Key: <your_key>`

The backend checks this value for admin-only endpoints. If missing or wrong, the request is rejected with `401 Unauthorized`.

Source of check:
- `app/security/auth.py` (`require_admin`)
- `app/main.py` admin routes

## 2) Where It Is Configured

- Local/dev: `.env` -> `ADMIN_API_KEY=...`
- Production: `.env.production` -> `ADMIN_API_KEY=...`

The key loaded in runtime must match what the caller sends in `X-API-Key`.

## 3) Exactly What This Key Can Access Today

Only these endpoints are protected by `X-API-Key` right now:

1. `GET /admin/leads`
2. `GET /admin/analytics/clicks-by-department`
3. `POST /admin/conversations/{id}/handoff`
4. `POST /admin/conversations/{id}/message`

Via nginx public routing, these are typically called as:

1. `GET /api/admin/leads`
2. `GET /api/admin/analytics/clicks-by-department`
3. `POST /api/admin/conversations/{id}/handoff`
4. `POST /api/admin/conversations/{id}/message`

## 4) What Admin Can See (Per Endpoint)

## 4.1 `GET /admin/leads`

Purpose:
- Inspect captured leads.

Response:
- `items` array of lead rows from Postgres (`leads` table), newest first.
- Query parameter:
  - `limit` (validated server-side to `1..500`, default `50`)

Fields visible:
- `id`
- `created_at`
- `name`
- `phone`
- `email`
- `project_type`
- `source`
- `session_id`

Operational use:
- Review incoming leads.
- Validate form ingestion.
- Spot source/session patterns.

## 4.2 `GET /admin/analytics/clicks-by-department`

Purpose:
- Inspect aggregated click analytics by project department/category.

Optional query params:
- `start` (datetime)
- `end` (datetime)

Response shape:
- `range` (`start`, `end`)
- `items` list of `{department, clicks}`
- `total_clicks`

Notes:
- Aggregates only click events (`project_category_click`).
- Null/blank department values are grouped as `unknown`.

Operational use:
- See top-clicked project sections.
- Compare department interest over a period.

## 5) What Admin CANNOT Manage With This Key (Current Scope)

Admin endpoints include read and controlled write actions (handoff status and outbound WhatsApp message).

Not available with this key today:
- Creating/updating/deleting leads
- Editing analytics rows
- Managing users/roles
- Rotating API keys through API
- Sending manual emails
- Triggering worker/admin jobs directly

So, today this key is for **inspection/reporting** plus **limited WhatsApp handoff controls**.

## 6) What Requires Admin API Key for Inspection

Use `X-API-Key` for:

1. Lead inspection (`/admin/leads`)
2. Aggregated analytics inspection (`/admin/analytics/clicks-by-department`)
3. Handoff status changes (`/admin/conversations/{id}/handoff`)
4. Manual WhatsApp message send (`/admin/conversations/{id}/message`)

No other route currently requires this key.

## 7) Practical Request Examples

## 7.1 View leads

```bash
curl -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  "http://127.0.0.1/api/admin/leads"
```

With limit:

```bash
curl -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  "http://127.0.0.1/api/admin/leads?limit=100"
```

## 7.2 View click counts by department

```bash
curl -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  "http://127.0.0.1/api/admin/analytics/clicks-by-department"
```

With date range:

```bash
curl -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  "http://127.0.0.1/api/admin/analytics/clicks-by-department?start=2026-02-01T00:00:00Z&end=2026-02-24T23:59:59Z"
```

## 7.3 Set handoff status (WhatsApp)

```bash
curl -X POST "http://127.0.0.1/api/admin/conversations/1/handoff" \
  -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  --data-raw '{"status":"human"}'
```

## 7.4 Send a manual WhatsApp message

```bash
curl -X POST "http://127.0.0.1/api/admin/conversations/1/message" \
  -H "X-API-Key: YOUR_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  --data-raw '{"text":"Hello from admin"}'
```

## 8) Security Rules for Admin API Key

Treat `ADMIN_API_KEY` like a password:

1. Do not expose it in frontend/widget code.
2. Do not commit real keys to git.
3. Store only in server env files or secret managers.
4. Rotate immediately if leaked.
5. Keep it long and random.
6. Share only with trusted admin operators.

Recommended:
- Restrict endpoint access at network layer (IP allowlist/VPN/reverse proxy auth) in addition to key.

## 9) Rotation Procedure (Simple and Safe)

1. Generate a new strong key.
2. Update `.env.production`:
   - `ADMIN_API_KEY=<new_value>`
3. Restart stack:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

4. Update admin clients/scripts to send new key.
5. Verify old key no longer works (expect `401`).

## 10) Quick Troubleshooting

`401 Unauthorized` on admin route:
- Check header name is exactly `X-API-Key`.
- Check runtime env has expected key.
- Check caller is hitting the correct environment/domain.
- Re-run with explicit curl header and inspect response.

Wrong/empty data:
- Confirm DB has records in `leads` / `analytics_events`.
- For analytics, verify click events include `department` (or legacy `category` mapped path).

`422` on `/admin/leads`:
- Check `limit` query value is within `1..500`.
