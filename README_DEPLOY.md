# OBE Bot Deployment (Docker Compose + Nginx)

Date: 2026-03-04  
Project Root: `d:\The Osiris Labs\obe-architects-bot`

## 1) Deployment Summary

This repository deploys a production-grade chatbot platform with:
- FastAPI backend
- Nginx serving widget assets and proxying API routes
- Redis session store
- Postgres + pgvector persistence
- Outbox + worker for SendGrid delivery
- Optional Ollama service for RAG

## 2) Server Prerequisites

```bash
sudo apt-get update
sudo apt-get install -y git curl
sudo apt-get install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

## 3) Clone and Configure

```bash
sudo mkdir -p /opt/obe-architects-bot
sudo chown -R "$USER":"$USER" /opt/obe-architects-bot
git clone <YOUR_REPO_URL> /opt/obe-architects-bot
cd /opt/obe-architects-bot
cp .env.production.example .env.production
```

Edit `.env.production` and set real values:
- `ADMIN_API_KEY`
- `POSTGRES_DSN`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `REDIS_URL`
- `SENDGRID_API_KEY`, `EMAIL_FROM`, `LEADS_NOTIFY_TO`
- WhatsApp env vars if enabled
- RAG env vars if enabled

## 4) Deploy

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Notes:
- Only `nginx` publishes ports (`80`, `443`).
- `db` and `redis` are internal-only on the backend network.
- `app`, `worker`, `db`, `redis`, `nginx`, `ollama` use `restart: unless-stopped`.
- `app` runs Alembic migrations if `alembic.ini` exists.
- When `RAG_ENABLED=true`, `python -m tools.rag migrate` runs at startup.

## 5) Verify Deployment

```bash
curl -i http://127.0.0.1/health
curl -I http://127.0.0.1/widget.js
curl -X POST http://127.0.0.1/api/chat/message \
  -H "Content-Type: application/json" \
  --data-raw '{"channel":"web","user_id":"deploy-smoke","session_id":null,"text":null,"button_id":null}'
```

Or run the smoke script:

```bash
bash scripts/smoke_test.sh http://127.0.0.1
```

## 6) Backup and Restore

Create backup:

```bash
bash scripts/backup_db.sh
```

Restore backup:

```bash
bash scripts/restore_db.sh ./backups/db_obe_bot_YYYYMMDD_HHMMSS.sql.gz
```

## 7) Update Procedure

```bash
cd /opt/obe-architects-bot
git pull --ff-only
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

## 8) Dependencies, Versions, and Frameworks

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

Infrastructure images:
- Postgres + pgvector: `pgvector/pgvector:pg16`
- Redis: `redis:7`
- Nginx: `nginx:alpine`
- Ollama (optional): `ollama/ollama:latest`

## 9) Project Plan (Ops-Oriented)

Phase 1 — Stabilization:
- Confirm TLS termination and domain routing.
- Validate CORS from production client site.

Phase 2 — Observability:
- Centralized logs and request metrics.
- Alerting for worker failures or email send errors.

Phase 3 — Data Governance:
- Regular backups and restore drills.
- Retention policy for lead and analytics data.

## 10) Scenario-Based File Edit Guide

Change deployment orchestration:
- `docker-compose.prod.yml`
- `docker/Dockerfile`
- `deploy/obe-chatbot.service`

Change routing or caching:
- `docker/nginx.conf`

Change env and secrets:
- `.env.production`
- `.env.production.example`

Change RAG infra:
- `docker-compose.prod.yml` (ollama service)
- `tools/rag/*` (migrations/loader)

## 11) File Use Map (High to Low Importance)

**High Importance**
- `docker-compose.prod.yml` — production orchestration.
- `docker/nginx.conf` — public routing and caching.
- `.env.production` — production configuration.
- `deploy.sh` — deployment workflow script.
- `deploy/obe-chatbot.service` — optional systemd service.
- `docker/Dockerfile` — app/worker image build.

**Medium Importance**
- `README.md` — developer and ops entrypoint.
- `OPERATIONS_RUNBOOK_2026-02-23.md` — operational checks.
- `PROJECT_HANDOFF_MASTER_2026-02-23.md` — master handoff.
- `PROJECT_OVERVIEW_AND_FEATURES_2026-02-24.md` — overview brief.

**Low Importance**
- `scripts/*` — helper scripts (smoke, backup, restore).
- `tests/*` — verification and regression checks.
- `docs/*` — supplementary docs.
