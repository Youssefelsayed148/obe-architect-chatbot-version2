# OBE Architects Bot - Project Overview and Capability Brief

Date: 2026-03-04  
Project Root: `d:\The Osiris Labs\obe-architects-bot`

## 1) Project Description

OBE Architects Bot is a production-grade, conversion-focused conversational assistant for OBE Architects.  
It combines an embeddable website widget, a FastAPI backend, Redis session memory, Postgres persistence, and a reliable email notification outbox/worker. It also includes WhatsApp Cloud API support and an optional RAG subsystem for grounded Q&A using the OBE website corpus.

Primary goals:
- Convert website visitors into qualified consultation leads.
- Provide operational visibility into lead flow and interest analytics.
- Enable secure admin controls and optional retrieval-augmented answers.

## 2) What Has Been Achieved (Current Stage)

Conversion and UX:
- Guided chat flow for project/service exploration.
- Consultation form capture with validation (name, phone, email).
- Post-submit success state with immediate WhatsApp contact CTA.
- Widget runtime API base configuration (no hardcoded localhost).

Reliability and delivery:
- Postgres outbox pattern for lead notifications.
- Worker with retries, attempts tracking, and terminal failure handling.
- SendGrid API integration (no SMTP).
- Graceful chat fallback if Redis is unavailable (`503`).

Analytics and visibility:
- Analytics event ingestion for project category clicks.
- Department-aware analytics aggregation.
- Admin endpoints protected by `X-API-Key`.

Channels and handoff:
- WhatsApp Cloud API webhook processing.
- Interactive menu flow + human handoff controls.

RAG (optional, admin-gated):
- Ingestion pipeline to scrape, clean, and chunk OBE site content.
- pgvector-backed retrieval and Ollama-based embeddings/chat.
- Admin-only RAG routes with feature gating via env vars.

## 3) High-Level Architecture

```text
Browser (Client Website)
  |
  | <script src="https://chatbot.domain/widget.js">
  v
Nginx (public entrypoint, :80/:443)
  |-- serves /widget.js + /widget.css from ./web
  |-- proxies /api/* -> app:8000/*
  |-- proxies /health -> app:8000/health
  |-- proxies /webhook/* -> app:8000/webhook/*
  v
FastAPI App (app.main:app, port 8000)
  |-- chat state machine + validation
  |-- consultation capture + analytics
  |-- admin endpoints + RAG (optional)
  |
  +--> Redis (sessions + rate limit)
  +--> Postgres (leads, analytics, conversations, email_outbox, vectors)
Worker (app.worker.email_worker)
  |-- polls email_outbox, retries, SendGrid delivery

Ollama (optional, used when RAG is enabled)
```

## 4) Project Structure (Functional Map)

Backend core:
- `app/main.py` — FastAPI app wiring, routes, middleware, static mount, optional RAG routes.
- `app/settings.py` — environment-driven settings.
- `app/bot/state_machine.py` — conversation logic and branching.
- `app/bot/content.py` — bot messages, buttons, and content payloads.
- `app/bot/validators.py` — contact and input validation.
- `app/store/postgres.py` — DB initialization and lead/analytics/outbox operations.
- `app/store/redis_sessions.py` — Redis session access.
- `app/worker/email_worker.py` — outbox polling and delivery.
- `app/services/email_sender.py` — SendGrid API client.
- `app/services/lead_email_templates.py` — lead email templates.
- `app/services/whatsapp_client.py` — WhatsApp send adapter.
- `app/webhooks/whatsapp.py` — WhatsApp webhook handling and handoff logic.
- `app/security/auth.py` — admin auth key validation.
- `app/middleware.py` — request-id and security headers middleware.
- `app/utils/rate_limit.py` — request throttling utility.

Widget:
- `web/widget.js` — embeddable chatbot script and API calls.
- `web/widget.css` — widget styling.

RAG and ingestion:
- `tools/ingestion/*` — scrape, clean, and chunk OBE site content.
- `tools/rag/*` — pgvector migrations, embeddings load, retrieval, smoke tests.

Deployment and ops:
- `docker/Dockerfile` — app/worker image.
- `docker/nginx.conf` — reverse proxy + static assets.
- `docker-compose.yml` — dev stack.
- `docker-compose.prod.yml` — production stack (includes pgvector + optional Ollama).
- `deploy.sh`, `deploy/*` — deploy artifacts.

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
- End-to-end production verification on Linux host.
- Confirm TLS termination and domain routing.
- Validate real browser CORS from production client site.

Phase 2 — Observability:
- Structured JSON logging.
- Request metrics and dashboards.
- Error alerting pipeline.

Phase 3 — Data and Governance:
- Migration workflow hardening (Alembic if required).
- Backups and restore drills.
- Data retention policy for leads/analytics.

Phase 4 — Product Enhancements:
- Multilingual support and expanded intents.
- Richer analytics taxonomy and funnel events.
- Accessibility and UX polish for widget.

## 7) Scenario-Based File Edit Guide (Quick Map)

Change bot behavior or buttons:
- `app/bot/state_machine.py`
- `app/bot/content.py`
- `app/schemas.py`

Change widget UI/UX:
- `web/widget.js`
- `web/widget.css`
- `web/widget.html`

Add or modify API endpoints:
- `app/main.py`
- `app/schemas.py`
- `app/store/postgres.py`
- `docker/nginx.conf` (if exposed via `/api`)

Update lead email content or delivery:
- `app/services/lead_email_templates.py`
- `app/services/email_sender.py`
- `app/worker/email_worker.py`

Update WhatsApp flow or handoff:
- `app/webhooks/whatsapp.py`
- `app/services/whatsapp_client.py`
- `app/security/auth.py` (admin controls)

Update RAG ingestion or retrieval:
- `tools/ingestion/*`
- `tools/rag/*`
- `app/rag/*`

Deployment or routing changes:
- `docker-compose.prod.yml`
- `docker/nginx.conf`
- `deploy.sh`
- `deploy/obe-chatbot.service`

## 8) File Use Map (High to Low Importance)

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
- `PROJECT_HANDOFF_MASTER_2026-02-23.md` — handoff details.

**Low Importance**
- `tests/*` — verification and regression checks.
- `test-client/test-client.html` — CORS and widget test harness.
- `scripts/*` — helper scripts (smoke, backup, restore).
- `docs/*` — supplementary docs.
- `data/ingestion/*` — generated ingestion outputs.
