# OBE Bot Operations Runbook

Date: 2026-03-04

## 1) Compose Files and Ports

Production-style stack:
- File: `docker-compose.prod.yml`
- Env file: `.env.production`
- Public nginx port: `80` (and `443` if TLS is terminated externally)

Development-style stack:
- File: `docker-compose.yml`
- Env file: `.env`
- Public nginx port: `8080` (mapped via compose if you change ports)

Production stack services:
- `app`
- `worker`
- `db`
- `redis`
- `nginx`
- `ollama` (optional, used when RAG is enabled)

Required email notification env vars:
- `SENDGRID_API_KEY`
- `EMAIL_FROM`
- `LEADS_NOTIFY_TO`

WhatsApp Cloud API env vars (if enabled):
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_GRAPH_VERSION` (default `v20.0`)
- `WHATSAPP_APP_SECRET` (optional)
- `HANDOFF_NOTIFY_TO` (optional; falls back to `LEADS_NOTIFY_TO`)

RAG env vars (if enabled):
- `RAG_ENABLED=true`
- `OLLAMA_BASE_URL` (default `http://localhost:11434`)
- `OLLAMA_EMBED_MODEL`
- `OLLAMA_CHAT_MODEL`
- `RAG_MIN_SCORE`
- `RAG_TOP_K`
- `RAG_MAX_CONTEXT_CHARS`
- `RAG_EMBED_DIM`

## 2) Start / Build / Stop

### 2.1 Build and start (production-style)

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

### 2.2 Start without rebuild

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

### 2.3 Stop stack

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down
```

## 3) Reset / Delete Containers and Volumes

### 3.1 Remove containers only (keeps DB data)

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down
```

### 3.2 Full reset (deletes DB volume and all data)

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down -v
docker volume ls
```

Warning: `down -v` is destructive for Postgres data.

### 3.3 Clean unused Docker resources (optional)

```bash
docker system prune -f
```

## 4) Health and Basic Verification

### 4.1 Service status

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Expected: `app`, `db`, `redis` are healthy; `worker`, `nginx`, and optional `ollama` are up.

### 4.2 Health endpoint via nginx

```bash
curl -i http://127.0.0.1/health
```

Expected: `HTTP/1.1 200 OK` and JSON body similar to:

```json
{"ok":true,"env":"production"}
```

### 4.3 Widget static files via nginx

```bash
curl -I http://127.0.0.1/widget.js
curl -I http://127.0.0.1/widget.css
```

Expected:
- Status `200 OK`
- `Cache-Control: public, max-age=3600`

### 4.4 Webhook verification (WhatsApp)

```bash
curl -i "http://127.0.0.1/webhook/whatsapp?hub.verify_token=replace_me&hub.challenge=abc123"
```

Expected:
- `HTTP/1.1 200 OK`
- Body `abc123`

## 5) API Tests

### 5.1 Chat endpoint

```bash
curl -X POST http://127.0.0.1/api/chat/message \
  -H "Content-Type: application/json" \
  --data-raw '{"channel":"web","user_id":"demo-user","session_id":null,"text":null,"button_id":null}'
```

Expected JSON fields:
- `session_id`
- `messages`
- `buttons`

### 5.2 Consultation endpoint

```bash
curl -X POST http://127.0.0.1/api/consultation/request \
  -H "Content-Type: application/json" \
  --data-raw '{"name":"Demo User","phone":"+971501234567","email":"demo@example.com","consultant_type":"Architectural Design","source":"chatbot","session_id":"s_demo_001"}'
```

Expected:
- `HTTP 200`
- JSON with `ok: true` and `lead_id`
- A new `email_outbox` row should be created asynchronously for worker pickup
- Widget UX should show the WhatsApp CTA on success

### 5.3 Analytics endpoint

```bash
curl -X POST http://127.0.0.1/api/analytics/event \
  -H "Content-Type: application/json" \
  --data-raw '{"event_name":"project_category_click","department":"Residential","category":"Villas","url":"https://example.com/projects","session_id":"s_demo_001","user_id":"demo-user","source":"chatbot"}'
```

Expected:
- `HTTP 201`
- JSON with `ok: true`

### 5.4 Admin analytics aggregation endpoint

```bash
curl -H "X-API-Key: replace_with_long_random_admin_key" \
  "http://127.0.0.1/api/admin/analytics/clicks-by-department"
```

Expected:
- `HTTP 200`
- JSON with:
  - `range`
  - `items` (department + clicks)
  - `total_clicks`

### 5.5 Admin handoff controls (WhatsApp)

```bash
curl -X POST http://127.0.0.1/api/admin/conversations/1/handoff \
  -H "X-API-Key: replace_with_long_random_admin_key" \
  -H "Content-Type: application/json" \
  --data-raw '{"status":"human"}'
```

```bash
curl -X POST http://127.0.0.1/api/admin/conversations/1/message \
  -H "X-API-Key: replace_with_long_random_admin_key" \
  -H "Content-Type: application/json" \
  --data-raw '{"text":"Hello from admin"}'
```

### 5.6 RAG (optional)

If `RAG_ENABLED=true` and the RAG schema is migrated:

```bash
curl -X POST http://127.0.0.1/admin/rag/ask \
  -H "X-API-Key: replace_with_long_random_admin_key" \
  -H "Content-Type: application/json" \
  --data-raw '{"question":"Do you design villas?","top_k":5}'
```

## 6) Database and Redis Tests

### 6.1 Postgres connectivity check

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec db \
  psql -U obe_user -d obe_bot -c "SELECT NOW();"
```

### 6.2 Check leads table count

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec db \
  psql -U obe_user -d obe_bot -c "SELECT COUNT(*) FROM leads;"
```

### 6.3 View latest leads rows

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec db \
  psql -U obe_user -d obe_bot -c "SELECT id, created_at, name, phone, email, project_type, source, session_id FROM leads ORDER BY id DESC LIMIT 10;"
```

### 6.4 View latest analytics rows

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec db \
  psql -U obe_user -d obe_bot -c "SELECT id, created_at, event_name, department, category, url, session_id, user_id, source FROM analytics_events ORDER BY id DESC LIMIT 20;"
```

### 6.5 View analytics aggregation directly in SQL

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec db \
  psql -U obe_user -d obe_bot -c "SELECT COALESCE(NULLIF(BTRIM(department), ''), 'unknown') AS department, COUNT(*) AS clicks FROM analytics_events WHERE event_name='project_category_click' GROUP BY 1 ORDER BY clicks DESC, department ASC;"
```

### 6.6 View latest outbox rows

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec db \
  psql -U obe_user -d obe_bot -c "SELECT id, event_key, lead_id, to_email, status, attempts, last_error, created_at, sent_at FROM email_outbox ORDER BY id DESC LIMIT 20;"
```

### 6.7 View latest WhatsApp conversations

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec db \
  psql -U obe_user -d obe_bot -c "SELECT id, channel, external_user_id, session_id, state, handoff_status, created_at, updated_at FROM conversations ORDER BY id DESC LIMIT 20;"
```

### 6.8 View latest WhatsApp messages

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec db \
  psql -U obe_user -d obe_bot -c "SELECT id, conversation_id, direction, provider_message_id, created_at FROM messages ORDER BY id DESC LIMIT 20;"
```

### 6.9 Redis ping

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec redis redis-cli ping
```

Expected: `PONG`

## 7) Logs and Monitoring Commands

### 7.1 Tail all logs

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f
```

### 7.2 Tail app and nginx logs

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f app nginx
```

### 7.3 Tail worker logs

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f worker
```

### 7.4 Last 200 app + worker log lines

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs app worker --tail=200
```

### 7.5 Container resource usage

```bash
docker stats
```

## 8) Test Client Page (Widget End-to-End)

### 8.1 Start local test page server

```bash
cd test-client
python -m http.server 5500
```

Open:
- `http://localhost:5500/test-client.html`

The file should include:

```html
window.OBE_CHATBOT_CONFIG = { apiBase: "http://127.0.0.1" };
<script src="http://127.0.0.1/widget.js" defer></script>
```

### 8.2 What success looks like

- Widget launcher appears.
- Chat panel opens.
- Initial bot response appears.
- Button clicks continue conversation.
- Consultation submit shows WhatsApp CTA.

## 9) Common Issues and Fixes

### 9.1 App unhealthy due to Postgres auth failure

Symptom in logs:
- `password authentication failed for user "obe_user"`

Fix:
1. Ensure `.env.production` `POSTGRES_DSN` password matches DB password.
2. Ensure `docker-compose.prod.yml` `POSTGRES_PASSWORD` matches same password.
3. If this is disposable local data, reset volume:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml down -v
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

### 9.2 CORS blocked in browser

Fix:
1. Add exact frontend origin to `ALLOWED_ORIGINS` in `.env.production`.
2. Recreate services:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

Expected local-testing entries in `.env.production`:
- `http://localhost:5500`
- `http://127.0.0.1:5500`

### 9.3 Wrong API base in test page

For production-style compose (`80:80`), use:
- `http://127.0.0.1`

For dev-style compose (`8080:80`), use:
- `http://127.0.0.1:8080`

### 9.4 SendGrid sender/auth or API key issues

Symptoms:
- Worker logs show SendGrid API 4xx with sender/auth errors
- `email_outbox.last_error` contains SendGrid rejection details

Fix:
1. Verify `SENDGRID_API_KEY`, `EMAIL_FROM`, `LEADS_NOTIFY_TO` in `.env.production`.
2. In SendGrid: `Settings -> Sender Authentication -> Single Sender Verification`.
3. Verify the sender mailbox.
4. Restart services:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

### 9.5 Outbox stuck in pending/failed

Checks:
1. Confirm worker is running:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

2. Inspect worker logs:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200 worker
```

3. Inspect outbox rows and attempts:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec db \
  psql -U obe_user -d obe_bot -c "SELECT id, event_key, status, attempts, last_error FROM email_outbox ORDER BY id DESC LIMIT 30;"
```

### 9.6 Chat requests fail with 503

Symptom:
- `/api/chat/message` returns `503` with `Service temporarily unavailable.`

Meaning:
- Redis dependency for session/rate-limit path is unavailable or timing out.

Checks:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200 redis app
```

Fix:
1. Ensure `redis` is healthy.
2. Ensure `REDIS_URL` points to reachable redis service.
3. Restart stack after config fix.

## 10) One-Command Deployment Script

Use:

```bash
chmod +x deploy.sh
./deploy.sh
```

It performs:
- `git pull --ff-only`
- build
- up
- status
- health probe
- recent logs

## 11) Scenario-Based File Edit Guide

Change chat behavior:
- `app/bot/state_machine.py`
- `app/bot/content.py`

Change widget UI:
- `web/widget.js`
- `web/widget.css`

Change database logic:
- `app/store/postgres.py`
- `app/schemas.py`

Change delivery/outbox:
- `app/worker/email_worker.py`
- `app/services/email_sender.py`
- `app/services/lead_email_templates.py`

Change WhatsApp flow:
- `app/webhooks/whatsapp.py`
- `app/services/whatsapp_client.py`

Change RAG:
- `tools/ingestion/*`
- `tools/rag/*`
- `app/rag/*`

Change deployment/routing:
- `docker-compose.prod.yml`
- `docker/nginx.conf`
- `deploy.sh`

## 12) File Use Map (High to Low Importance)

**High Importance**
- `app/main.py` — API routes, middleware, and optional RAG wiring.
- `app/settings.py` — environment configuration.
- `app/bot/state_machine.py` — core chat logic.
- `app/bot/content.py` — chat content and button payloads.
- `app/bot/validators.py` — input validation.
- `app/store/postgres.py` — DB persistence for leads/analytics/outbox.
- `app/store/redis_sessions.py` — Redis session and rate-limit state.
- `app/worker/email_worker.py` — outbox delivery worker.
- `app/services/email_sender.py` — SendGrid sending.
- `app/services/lead_email_templates.py` — email templates.
- `app/webhooks/whatsapp.py` — WhatsApp webhook logic.
- `app/services/whatsapp_client.py` — WhatsApp API calls.
- `app/security/auth.py` — admin auth checks.
- `app/middleware.py` — request ID and security headers.
- `app/utils/rate_limit.py` — rate limiting.
- `web/widget.js` — widget behavior and API calls.
- `web/widget.css` — widget styling.
- `docker-compose.prod.yml` — production orchestration.
- `docker/nginx.conf` — public routing and caching.
- `.env.production` — production configuration.
- `requirements.txt` — runtime dependency pins.

**Medium Importance**
- `app/schemas.py` — request/response contracts.
- `app/rag/*` — RAG query, retrieval, and answer assembly.
- `tools/rag/*` — RAG migrations and embeddings load.
- `tools/ingestion/*` — scrape, clean, and chunk pipeline.
- `docker-compose.yml` — dev orchestration.
- `docker/Dockerfile` — app image build.
- `.env.example` — environment template.
- `README.md` — developer and ops entrypoint.
- `README_DEPLOY.md` — server deployment steps.
- `PROJECT_OVERVIEW_AND_FEATURES_2026-02-24.md` — overview brief.
- `PROJECT_HANDOFF_MASTER_2026-02-23.md` — master handoff.

**Low Importance**
- `tests/*` — verification and regression checks.
- `test-client/test-client.html` — CORS and widget test harness.
- `scripts/*` — helper scripts (smoke, backup, restore).
- `docs/*` — supplementary docs.
- `data/ingestion/*` — generated ingestion outputs.
