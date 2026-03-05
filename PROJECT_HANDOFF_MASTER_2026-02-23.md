# OBE Architects Bot - Master Handoff

Date: 2026-03-04  
Project Root: `d:\The Osiris Labs\obe-architects-bot`

## 1) Executive Summary

This repository is a production-oriented chatbot platform for OBE Architects.  
It includes a FastAPI backend, Redis session store, Postgres persistence, a widget served by Nginx, reliable SendGrid outbox delivery, WhatsApp Cloud API support, and an optional RAG subsystem using pgvector + Ollama.

At this stage the system supports:
- Guided chat flow with consultation capture.
- Postgres outbox + worker for reliable email notifications.
- Analytics ingestion and admin aggregation by department.
- Secure admin endpoints protected by `X-API-Key`.
- Static widget assets served by Nginx.
- WhatsApp channel adapter with human handoff.
- Optional ingestion + RAG for grounded Q&A.

## 2) What Was Achieved in This Stage

### 2.1 Infrastructure and Routing
- Nginx serves widget assets directly:
  - `GET /widget.js`
  - `GET /widget.css`
- Nginx proxies API through stable prefix:
  - `/api/* -> app:8000/*`
- Nginx proxies health:
  - `GET /health -> app:8000/health`
- Nginx proxies webhooks:
  - `GET/POST /webhook/* -> app:8000/webhook/*`
- Gzip enabled for text/js/css/json/xml/svg.
- Cache headers:
  - Widget assets: `Cache-Control: public, max-age=3600`
  - HTML/fallback: `Cache-Control: no-store`

File: `docker/nginx.conf`

### 2.2 Widget Runtime Config
- `window.OBE_CHATBOT_CONFIG.apiBase` is supported.
- Default API base is same-origin when config is missing.
- Widget calls use `${apiBase}/api/...`.
- Widget auto-injects required HTML and CSS.
- Project cards include `Request a consultation`.
- Consultation success state shows immediate WhatsApp CTA.

File: `web/widget.js`

### 2.3 Backend CORS Hardening
Allowed origins are restricted to:
- `https://obearchitects.com`
- `https://www.obearchitects.com`
- `http://client.local:5500`
- `http://localhost:5500`

Files:
- `app/settings.py`
- `.env`
- `.env.example`
- `.env.production`

### 2.4 Health and Compose Reliability
Health checks added for:
- `app` (HTTP probe to `/health`)
- `db` (`pg_isready`)
- `redis` (`redis-cli ping`)

Compose dependency gating uses health status:
- `app` waits for healthy `db` and `redis`
- `nginx` waits for healthy `app`

Files:
- `docker-compose.yml`
- `docker-compose.prod.yml`

### 2.5 Delivery and Operations Artifacts
Added:
- `docker-compose.prod.yml` (includes pgvector and optional Ollama)
- `.env.production` (example values only)
- `deploy.sh` (pull, build, up, health/log checks)
- `deploy/obe-chatbot.service` (optional systemd auto-start)
- `test-client/test-client.html` (cross-origin embed test page)
- README updates

### 2.6 Analytics Aggregation Enhancements
- Analytics events persist `department`.
- Backward compatibility for legacy `category`.
- Admin endpoint:
  - `GET /admin/analytics/clicks-by-department?start=...&end=...`
- Aggregation:
  - Filters to `event_name = 'project_category_click'`
  - Groups by department
  - Normalizes null/blank to `unknown`
  - Returns grouped counts and `total_clicks`
- Added index:
  - `(event_name, department, created_at)`

### 2.7 Lead Notification Outbox + Worker
- Lead creation enqueues notification in `email_outbox` in same DB transaction.
- Outbox idempotency key: `lead_notify:<lead_id>` (`UNIQUE event_key`).
- Worker polls pending rows with `FOR UPDATE SKIP LOCKED`, increments attempts, and marks:
  - `sent` on success (`sent_at` set)
  - `pending` with `last_error` on retryable failure
  - `failed` when attempts reach 8

### 2.8 WhatsApp Cloud API Channel + Handoff
- Incoming webhook handler with verification + optional signature validation.
- Menu-driven WhatsApp flow with interactive buttons and list.
- Conversation persistence and message deduplication.
- Human handoff stops bot replies and enqueues `handoff_requested` email.
- Admin endpoints to toggle handoff status or send a manual WhatsApp message.

### 2.9 RAG Ingestion + Retrieval (Optional, Admin-Gated)
- Scrape, clean, and chunk the OBE site into JSONL.
- pgvector schema and migrations via `tools/rag`.
- Embeddings and chat through Ollama.
- Admin-only routes mounted when `RAG_ENABLED=true`.
- Optional public RAG route controlled by `RAG_PUBLIC_ENABLED=true`.

### 2.10 Production Hardening Updates
- Chat returns `503` when Redis is unavailable.
- Redis clients include socket connect/read timeouts.
- Admin leads endpoint validates `limit` (`1..500`).
- Request logging uses the configured logger.
- Webhook verify handlers return challenge safely without integer conversion.
- WhatsApp webhook validates signature when `WHATSAPP_APP_SECRET` is present.
- Fixed welcome text encoding artifacts.

## 3) High-Level Architecture

```text
Browser (Client Website)
  |
  | <script src="https://chatbot.domain/widget.js">
  v
Nginx (public entrypoint, :80/:443 at edge)
  |-- serves /widget.js + /widget.css from ./web
  |-- proxies /health -> app:8000/health
  |-- proxies /api/* -> app:8000/*
  |-- proxies /webhook/* -> app:8000/webhook/*
  v
FastAPI App (app.main:app, port 8000)
  |-- state machine + validation
  |-- rate limiting + middleware
  |-- endpoints: chat, consultation, analytics, admin, webhooks, optional RAG
  |
  +--> Redis (session/state support)
  +--> Postgres (leads + analytics + conversations + messages + email_outbox + vectors)
Worker (app.worker.email_worker)
  |-- polls email_outbox
  |-- retries + terminal failure handling
  |-- sends notifications via SendGrid API

Ollama (optional, for RAG embeddings + chat)
```

## 4) Project Structure and Responsibilities

Core backend:
- `app/main.py`
- `app/settings.py`
- `app/schemas.py`
- `app/bot/state_machine.py`
- `app/bot/content.py`
- `app/bot/validators.py`
- `app/store/postgres.py`
- `app/store/redis_sessions.py`
- `app/security/auth.py`
- `app/utils/rate_limit.py`
- `app/middleware.py`

Email and worker:
- `app/services/lead_email_templates.py`
- `app/services/email_sender.py`
- `app/worker/email_worker.py`

WhatsApp:
- `app/webhooks/whatsapp.py`
- `app/services/whatsapp_client.py`

RAG:
- `app/rag/*`
- `tools/ingestion/*`
- `tools/rag/*`

Frontend widget:
- `web/widget.js`
- `web/widget.css`
- `web/widget.html`
- `app/static/chatbot/thumbs/*`

Deployment:
- `docker/Dockerfile`
- `docker/nginx.conf`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `.env.example`
- `.env.production`
- `deploy.sh`
- `deploy/obe-chatbot.service`

Testing and harness:
- `tests/*`
- `test-client/test-client.html`

## 5) API and Entrypoints

App process entrypoint:
- `uvicorn app.main:app --host=0.0.0.0 --port=8000`

HTTP endpoints:
- `GET /health`
- `POST /chat/message`
- `POST /consultation/request`
- `POST /analytics/event`
- `GET /admin/leads`
- `GET /admin/analytics/clicks-by-department`
- `POST /admin/conversations/{id}/handoff`
- `POST /admin/conversations/{id}/message`
- `GET/POST /webhook/instagram`
- `GET/POST /webhook/whatsapp`
- `POST /chat/ask` (optional public RAG, gated by `RAG_PUBLIC_ENABLED`)
- `POST /admin/rag/ask` (admin-only RAG)

Nginx public paths:
- `GET /widget.js`
- `GET /widget.css`
- `GET /health`
- `POST /api/chat/message`
- `POST /api/consultation/request`
- `POST /api/analytics/event`
- `GET /api/admin/analytics/clicks-by-department`
- `POST /api/admin/conversations/{id}/handoff`
- `POST /api/admin/conversations/{id}/message`
- `GET/POST /webhook/instagram`
- `GET/POST /webhook/whatsapp`

## 6) Dependencies, Versions, and Frameworks

Python runtime:
- Base image: `python:3.11-slim`
- FastAPI `0.115.0`
- Uvicorn `0.30.6`
- Pydantic `2.8.2`
- python-dotenv `1.0.1`
- redis client `5.0.8`
- psycopg[binary] `3.2.1`
- SendGrid `6.11.0`
- httpx `0.27.2`
- beautifulsoup4 `4.12.3`
- trafilatura `1.12.2`
- lxml `5.3.0`
- tldextract `5.1.2`
- tenacity `9.0.0`

Test dependencies:
- pytest `8.3.3`
- pytest-asyncio `0.24.0`

Infrastructure images:
- Postgres + pgvector: `pgvector/pgvector:pg16`
- Redis: `redis:7`
- Nginx: `nginx:alpine`
- Ollama (optional): `ollama/ollama:latest`

## 7) Scenario-Based File Edit Guide

Change chat flow and content:
- `app/bot/state_machine.py`
- `app/bot/content.py`
- `app/bot/validators.py`
- `app/schemas.py`

Add or modify API endpoints:
- `app/main.py`
- `app/schemas.py`
- `app/store/postgres.py`
- `docker/nginx.conf` (if exposed via `/api`)

Widget UI/UX changes:
- `web/widget.js`
- `web/widget.css`
- `web/widget.html`

Lead email notification changes:
- `app/services/lead_email_templates.py`
- `app/services/email_sender.py`
- `app/worker/email_worker.py`
- `.env.production` (SendGrid vars)

WhatsApp flow changes:
- `app/webhooks/whatsapp.py`
- `app/services/whatsapp_client.py`
- `.env.production` (WhatsApp vars)

RAG ingestion or retrieval changes:
- `tools/ingestion/*`
- `tools/rag/*`
- `app/rag/*`

Deployment and routing:
- `docker-compose.prod.yml`
- `docker/nginx.conf`
- `deploy.sh`
- `deploy/obe-chatbot.service`

## 8) Project Plan (Next Iterations)

Phase 1 — Stabilization:
- Verify production routing and TLS.
- Validate CORS from production client origin.

Phase 2 — Observability:
- Structured JSON logs and metrics.
- Error alerting pipeline.

Phase 3 — Data Governance:
- Backups, restore drills, retention policy.

Phase 4 — Product Enhancements:
- Multilingual intents and richer analytics.

## 9) File Use Map (High to Low Importance)

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
- `OPERATIONS_RUNBOOK_2026-02-23.md` — operational checks.
- `PROJECT_OVERVIEW_AND_FEATURES_2026-02-24.md` — overview brief.

**Low Importance**
- `tests/*` — verification and regression checks.
- `test-client/test-client.html` — CORS and widget test harness.
- `scripts/*` — helper scripts (smoke, backup, restore).
- `docs/*` — supplementary docs.
- `data/ingestion/*` — generated ingestion outputs.
