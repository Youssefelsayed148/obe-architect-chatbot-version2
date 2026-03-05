# OBE Architects Bot

Date: 2026-03-04  
Project Root: `d:\The Osiris Labs\obe-architects-bot`

## 1) Overview

OBE Architects Bot is a production-grade chatbot platform that combines:
- An embeddable website widget.
- A FastAPI backend with Redis session state and Postgres persistence.
- A reliable email notification outbox + worker using SendGrid.
- WhatsApp Cloud API support with human handoff.
- Optional RAG for grounded answers using pgvector + Ollama.

Primary goals:
- Convert site visitors into qualified consultation leads.
- Provide operational visibility via analytics and admin endpoints.
- Support both web and WhatsApp channels.

## 2) Current Feature Set (What We Have Achieved)

Conversion and UX:
- Guided chat flow for service/project exploration.
- Consultation form capture with validation.
- Post-submit success state with immediate WhatsApp CTA.
- Runtime-configurable API base in widget.

Reliability and delivery:
- Postgres outbox pattern for lead notifications.
- Retry-safe worker and terminal failure handling.
- SendGrid API delivery (no SMTP).
- Graceful chat fallback if Redis is unavailable (`503`).

Analytics and admin:
- Analytics ingestion for project category clicks.
- Department-based aggregation endpoint.
- Admin endpoints protected by `X-API-Key`.

WhatsApp:
- Webhook verification + optional signature validation.
- Menu-driven flow with human handoff controls.

RAG (optional):
- Site scraping + cleaning + chunking pipeline.
- pgvector-backed retrieval.
- Ollama embeddings and chat generation.
- Admin-only RAG routes (and optional public endpoint).

## 3) High-Level Architecture

```text
Browser (Client Website)
  |
  | <script src="https://chatbot.domain/widget.js">
  v
Nginx (public entrypoint, :80/:443)
  |-- serves /widget.js + /widget.css
  |-- proxies /api/* -> app:8000/*
  |-- proxies /health -> app:8000/health
  |-- proxies /webhook/* -> app:8000/webhook/*
  v
FastAPI App (app.main:app, port 8000)
  |-- chat + consultation + analytics + admin + optional RAG
  |
  +--> Redis (session/state)
  +--> Postgres (leads, analytics, conversations, outbox, vectors)
Worker (app.worker.email_worker)
  |-- polls email_outbox, retries, SendGrid delivery

Ollama (optional, for RAG embeddings + chat)
```

## 4) Project Structure (Key Areas)

Backend:
- `app/main.py`
- `app/settings.py`
- `app/bot/*`
- `app/store/*`
- `app/services/*`
- `app/worker/*`
- `app/webhooks/*`
- `app/rag/*`

Widget:
- `web/widget.js`
- `web/widget.css`

Ingestion/RAG:
- `tools/ingestion/*`
- `tools/rag/*`

Deployment:
- `docker/Dockerfile`
- `docker/nginx.conf`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `deploy.sh`
- `deploy/*`

## 5) Dependencies, Versions, and Frameworks

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

## 6) Project Plan (Next Iterations)

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

## 7) Local Development (Windows)

### 7.1 Create and activate virtual environment

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

cmd:

```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
```

### 7.2 Install dependencies

```powershell
pip install -r requirements-dev.txt
```

`psycopg[binary]` is pinned in `requirements.txt`, which is recommended for Windows local development.

### 7.3 Configure environment

PowerShell:

```powershell
Copy-Item .env.example .env
```

cmd:

```cmd
copy .env.example .env
```

For local Docker runs, update `.env` to:

```env
REDIS_URL=redis://localhost:6379/0
POSTGRES_DSN=postgresql://obe_user:obe_pass@localhost:5432/obe_bot
SENDGRID_API_KEY=YOUR_REAL_KEY
EMAIL_FROM=jojgame10@gmail.com
LEADS_NOTIFY_TO=jojgame10@gmail.com
```

### 7.4 Start Postgres and Redis in Docker

```powershell
docker compose up -d db redis
docker compose ps
```

### 7.5 Run the API

Recommended:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or:

```cmd
scripts\run_api.bat
```

Worker (second terminal):

```powershell
python -m app.worker.email_worker
```

### 7.6 Run tests

Unit tests only:

```powershell
pytest -m "not integration" -q
```

Integration tests:

```powershell
pytest -m integration -q
```

## 8) Quick API Verification

Health:

```powershell
curl.exe http://127.0.0.1:8000/health
```

Chat:

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat/message `
  -H "Content-Type: application/json" `
  -d "{\"channel\":\"web\",\"user_id\":\"demo-user\",\"session_id\":null,\"text\":null,\"button_id\":null}"
```

Admin leads:

```powershell
curl.exe -H "X-API-Key: change_me_to_a_long_random_string" http://127.0.0.1:8000/admin/leads
```

Optional public RAG (if enabled):

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat/ask `
  -H "Content-Type: application/json" `
  -d "{\"user_id\":\"demo-user\",\"question\":\"Do you design villas?\",\"top_k\":5}"
```

## 9) Production Deployment (Server)

See `README_DEPLOY.md` for step-by-step Ubuntu instructions.

## 10) Scenario-Based File Edit Guide

Change chat behavior:
- `app/bot/state_machine.py`
- `app/bot/content.py`

Change widget UI/UX:
- `web/widget.js`
- `web/widget.css`

Add or modify API endpoints:
- `app/main.py`
- `app/schemas.py`
- `app/store/postgres.py`

Update lead email delivery:
- `app/services/lead_email_templates.py`
- `app/services/email_sender.py`
- `app/worker/email_worker.py`

Update WhatsApp flow:
- `app/webhooks/whatsapp.py`
- `app/services/whatsapp_client.py`

Update RAG:
- `tools/ingestion/*`
- `tools/rag/*`
- `app/rag/*`

Deployment changes:
- `docker-compose.prod.yml`
- `docker/nginx.conf`
- `deploy.sh`

## 11) File Use Map (High to Low Importance)

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
- `README_DEPLOY.md` — server deployment steps.
- `OPERATIONS_RUNBOOK_2026-02-23.md` — operational checks.
- `PROJECT_HANDOFF_MASTER_2026-02-23.md` — master handoff.
- `PROJECT_OVERVIEW_AND_FEATURES_2026-02-24.md` — overview brief.

**Low Importance**
- `tests/*` — verification and regression checks.
- `test-client/test-client.html` — CORS and widget test harness.
- `scripts/*` — helper scripts (smoke, backup, restore).
- `docs/*` — supplementary docs.
- `data/ingestion/*` — generated ingestion outputs.
