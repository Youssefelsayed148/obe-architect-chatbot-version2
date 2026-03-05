# OBE Architects Chatbot - Project State (Phase 3) V2 Complete

Date: 2026-02-27  
Repository: `d:\The Osiris Labs\obe-architects-bot`

## 1) Executive Summary

### What the chatbot does
The system is a FastAPI-based chatbot platform for OBE Architects with:
- Web chat flow (`/chat/message`) and consultation lead capture (`/consultation/request`)
- Analytics event ingestion (`/analytics/event`) and admin analytics aggregation
- WhatsApp webhook/channel support with human handoff controls
- Async lead/handoff email notifications via a Postgres outbox + worker
- Optional Phase 3 RAG endpoints for admin-only retrieval + answer generation

### What Phase 1, 2, and 3 accomplished
Based on current repository structure and docs (`docs/INGESTION_PHASE_0_1_2.md`, `docs/PHASE_3_RAG.md` before this update):
- Phase 1: Website scraping + extraction pipeline (`tools/ingestion/scrape_site.py`) with robots handling and structured discovery for OBE URLs.
- Phase 2: Cleaning and chunking (`tools/ingestion/chunk_docs.py`) to produce `data/ingestion/chunks/chunks.jsonl`.
- Phase 3: Local RAG stack using Ollama embeddings + chat generation and pgvector-backed retrieval (`app/rag/*`, `tools/rag/*`, `tools/rag/sql/001_pgvector_schema.sql`).

### What RAG adds to the system
RAG introduces:
- Vectorized chunk storage (`rag_chunks.embedding VECTOR(768)`) in PostgreSQL with pgvector
- Similarity search (`<=>` cosine distance) and score filtering
- Context-constrained prompt assembly + LLM answer generation
- Admin-only endpoints:
  - `POST /admin/rag/search`
  - `POST /admin/rag/answer`

### Production-ready vs isolated
Production-ready (implemented and integrated):
- Core chat, consultation, analytics, admin, webhook routes
- Redis sessions/rate limiting
- Postgres persistence + outbox worker
- Docker compose deployment + nginx reverse proxy

Isolated/feature-gated:
- RAG is isolated by `RAG_ENABLED` and mounted only when enabled (`app/main.py`)
- RAG endpoints are admin-only and not exposed through public chat flow
- Ollama is not defined as a compose service in this repo; it is external and must be reachable via `OLLAMA_BASE_URL`

## 2) Complete System Architecture

### Backend architecture
FastAPI composition (`app/main.py`):
- App setup: `FastAPI(title="OBE Bot API")`
- Middleware:
  - CORS middleware with `ALLOWED_ORIGINS`
  - `RequestIdAndSecurityHeadersMiddleware` for request IDs, security headers, structured logging
- Router layering:
  - Main routes declared directly in `app/main.py`
  - WhatsApp router mounted via `app.include_router(whatsapp_router)` from `app/webhooks/whatsapp.py`
  - RAG admin router conditionally included only if `settings.rag_enabled`
- Static mount: `/static` from `app/static`

X-API-Key protection model:
- Admin routes call `require_admin(x_api_key)` (`app/security/auth.py`)
- Validation is strict equality against `settings.admin_api_key`
- Protection is route-level guard (not a global authentication middleware)

Feature flags:
- `RAG_ENABLED` gates RAG router mounting and internal endpoint checks (`_ensure_enabled` in `app/rag/admin_routes.py`)

Admin isolation:
- Admin operations are separated under `/admin/*`
- RAG endpoints are further namespaced under `/admin/rag/*`

### Service architecture (Docker)
From `docker-compose.yml` and `docker-compose.prod.yml`:
- `app`: FastAPI API container from `docker/Dockerfile`
- `worker`: background email worker (`python -m app.worker.email_worker`)
- `db`: `pgvector/pgvector:pg16`
- `redis`: `redis:7`
- `nginx`: `nginx:alpine` serving widget assets + reverse proxy

Ollama service status:
- No `ollama` service is declared in compose files.
- Runtime uses `OLLAMA_BASE_URL` (default `http://localhost:11434`, local `.env` currently `http://host.docker.internal:11434`).

Internal communication paths:
- `nginx -> app:8000` for `/api/*`, `/webhook/*`, `/health`
- `app -> db` via `POSTGRES_DSN`
- `app -> redis` via `REDIS_URL`
- `worker -> db` for outbox polling/updates
- `app -> ollama` over HTTP (`/api/embeddings`, `/api/chat`) at `OLLAMA_BASE_URL`

## 3) Embeddings System (Detailed)

### Embedding model used
- Config variable: `OLLAMA_EMBED_MODEL`
- Current values in tracked env files:
  - `.env`: `nomic-embed-text`
  - `.env.production`: `nomic-embed-text`

### Where embeddings are generated
Runtime query embedding:
- `app/rag/retriever.py` calls `OllamaEmbedder().get_embeddings([query])`
- `OllamaEmbedder` uses `OllamaClient.embed()` -> POST to `{OLLAMA_BASE_URL}/api/embeddings`

Offline chunk embedding:
- `tools/rag/load_embeddings.py` builds batches from `chunks.jsonl`
- For each batch, it calls `embedder.get_embeddings([chunk_text...])`

### How embedding dimension is configured
- App setting: `RAG_EMBED_DIM` (`app/settings.py`), default `768`
- Embedder enforces dimension in `app/rag/embedder.py`:
  - Raises `ValueError` if actual vector length != expected dim

Important invariant:
- SQL schema hardcodes `embedding VECTOR(768)` in `tools/rag/sql/001_pgvector_schema.sql`
- Therefore `RAG_EMBED_DIM` must stay aligned with DB schema dimension.

### Batch loading behavior
`load_embeddings()` (`tools/rag/load_embeddings.py`):
- Reads JSONL line-by-line from `RAG_CHUNKS_PATH`
- Parses each line via `parse_chunk_line`
- Accumulates up to `batch_size` (`RAG_BATCH_SIZE`, default 64)
- Embeds batch, then upserts documents/chunks
- Supports:
  - `--limit` for partial runs
  - `--reembed` to update existing vectors/content

### CLI embedding loader logic
Entry: `python -m tools.rag load [--chunks-path ... --limit ... --reembed --batch-size ...]`
- CLI parser: `tools/rag/main.py`
- Subcommand dispatch: `tools/rag/__main__.py`

### How embeddings are stored in DB
- Table: `rag_chunks`
- Column: `embedding VECTOR(768) NOT NULL`
- Additional model traceability: `embedding_model TEXT NOT NULL`
- Unique key: `(document_url, chunk_index, embedding_model)`

### Consistency enforcement and mismatch behavior
Enforcement points:
- Application-level: `OllamaEmbedder` dimension check
- Database-level: vector column fixed at dimension 768

On mismatch:
- Embedder raises `ValueError`
- In loader `_flush_batch`, any exception increments `failures` by batch size and batch is not written
- At runtime retrieval, mismatch raises and request fails (no silent fallback)

### Performance implications
Current implementation implications:
- `OllamaEmbedder.get_embeddings()` loops one text at a time, invoking one HTTP call per text
- Batch size improves DB write grouping, but not embedding call concurrency
- Formatting vector literals to 8 decimals is deterministic but adds conversion overhead

### Safe embedding model swap
Required safe sequence:
1. Choose model and verify output dimension.
2. Update env `OLLAMA_EMBED_MODEL` and `RAG_EMBED_DIM`.
3. Update SQL schema dimension (`VECTOR(<new_dim>)`) in migration strategy.
4. Recreate vector schema/tables or create new schema path.
5. Re-embed all chunks (`python -m tools.rag load --reembed`).
6. Rebuild vector index.

### Where to edit configuration
- Runtime settings: `app/settings.py`
- Environment values: `.env`, `.env.production`, `.env.production.example`
- Vector schema dimension: `tools/rag/sql/001_pgvector_schema.sql`
- Loader defaults/flags: `tools/rag/main.py`, `tools/rag/load_embeddings.py`

## 4) Vector Database (pgvector) Internals

### pgvector extension
Migration starts with:
- `CREATE EXTENSION IF NOT EXISTS vector;`

### Schema and table design
`tools/rag/sql/001_pgvector_schema.sql` creates:
- `rag_documents`
  - metadata keyed by unique `url`
- `rag_chunks`
  - per-chunk text + vector + model
  - FK `document_url -> rag_documents(url)` with `ON DELETE CASCADE`

### Vector column type
- `embedding VECTOR(768) NOT NULL`

### Index type and metric
- Index: IVFFlat
- SQL:
  - `USING ivfflat (embedding vector_cosine_ops)`
  - `WITH (lists = 100)`
- Metric operator in retrieval:
  - `<=>` with cosine ops

### Similarity scoring formula
In `app/rag/retriever.py`:
- Distance ordering: `ORDER BY rc.embedding <=> %s::vector`
- Returned score: `score = 1 - (rc.embedding <=> %s::vector)`

Interpretation:
- Higher score = more similar (for cosine distance-based retrieval)

### How `RAG_MIN_SCORE` works
- Top-K is fetched first in SQL (`LIMIT %s`)
- Python then filters fetched matches with `item["score"] >= use_min_score`
- This means low-score items can reduce final count below `top_k`

### How `top_k` interacts with scoring
- `top_k` controls SQL retrieval window only.
- Final output size after `RAG_MIN_SCORE` filter may be `< top_k`.

### Migration file structure and application
- Migration runner: `tools/rag/migrate.py`
- Default SQL path: `tools/rag/sql/001_pgvector_schema.sql`
- Apply via: `python -m tools.rag migrate`

### Safe reinitialize pattern
Current repo has no migration framework versioning beyond this SQL file. Safe reset pattern:
1. Backup DB data if needed.
2. Drop/recreate `rag_chunks` and `rag_documents` (or reset entire DB volume in non-prod).
3. Run migration command.
4. Reload embeddings.
5. Run smoke test.

### Inspect vector data via psql
Examples:
```sql
SELECT COUNT(*) FROM rag_documents;
SELECT COUNT(*) FROM rag_chunks;
SELECT id, document_url, chunk_index, embedding_model FROM rag_chunks ORDER BY id DESC LIMIT 10;
SELECT embedding <=> '[0.1,0.2,...]'::vector FROM rag_chunks LIMIT 1;
\d+ rag_chunks
```

### Scaling considerations
- IVFFlat performance depends on list sizing and data distribution.
- Single-table design is simple but can grow large; partitioning/sharding is not implemented.
- Query pipeline is synchronous and tied to app request path.

### Index rebuild considerations
- File comment states IVFFlat performs best after substantial data load.
- Recommended maintenance action after large re-embeds:
```sql
REINDEX INDEX idx_rag_chunks_embedding_ivfflat;
```

### Performance tuning options (current stack)
- Increase/decrease `RAG_TOP_K` based on latency vs recall
- Tune `RAG_MIN_SCORE` to reduce low-relevance context
- Tune `RAG_MAX_CONTEXT_CHARS` to reduce token pressure
- Revisit IVFFlat `lists` parameter in SQL for corpus size
- Consider batching/concurrency improvements in embedding calls (code change required)

## 5) Retrieval Pipeline

End-to-end sequence implemented by `app/rag/retriever.py` + `app/rag/rag_answer.py`:
1. User query received on admin RAG endpoint.
2. Query embedding generated with Ollama embedding model.
3. Vector similarity SQL search in `rag_chunks` joined with `rag_documents`.
4. Score computed as `1 - cosine_distance`.
5. SQL returns ordered top-K by smallest distance.
6. Python score filtering (`RAG_MIN_SCORE`).
7. Context assembly in `_build_context()` with numbered blocks (URL/title/score/chunk).
8. Context truncation by character budget (`RAG_MAX_CONTEXT_CHARS`) using additive-fit policy.
9. Prompt construction:
   - System: "Use ONLY provided context. If not found, say you don't know."
   - User: question + assembled context or "No matching context found."
10. LLM chat call via Ollama `/api/chat`.
11. Response parsing (`message.content`, fallback `response`, fallback OpenAI-like choice shape).
12. Final payload returns `answer`, `sources`, and `matches`.

Hallucination risk reduction currently implemented:
- Restrictive system prompt requiring context-only answers
- Optional min-score filtering
- Explicit no-context marker in prompt when retrieval is empty

Context size control:
- Hard cap: `RAG_MAX_CONTEXT_CHARS`
- Block-level inclusion skips blocks that exceed remaining budget

Fallback behavior:
- No dedicated alternate answer path exists.
- If no matches survive filtering, LLM still receives prompt with `No matching context found.`

## 6) RAG Module Structure

### `app/rag/embedder.py`
Responsibility:
- `OllamaEmbedder` wrapper around Ollama embeddings
- Model selection + expected dimension enforcement

### `app/rag/retriever.py`
Responsibility:
- Defines retrieval SQL and score expression
- Generates query embedding
- Executes vector query against Postgres
- Applies `RAG_MIN_SCORE` filtering
- Normalizes returned match dict shape

### `app/rag/rag_answer.py`
Responsibility:
- Calls retriever
- Builds bounded context blocks and source URL list
- Constructs final prompt
- Calls chat model and returns response package

### `app/rag/ollama_client.py`
Responsibility:
- HTTP client wrapper for Ollama
- Retry strategy (`tenacity`: up to 3 attempts, exponential backoff)
- Response-shape parsing for embeddings and chat outputs

### `app/rag/admin_routes.py`
Responsibility:
- Admin API surface for RAG
- Enforces `RAG_ENABLED` and `X-API-Key` admin auth
- Exposes `/admin/rag/search` and `/admin/rag/answer`

### `tools/rag/migrate.py`
Responsibility:
- Applies SQL schema migration file for pgvector objects

### `tools/rag/load_embeddings.py`
Responsibility:
- Reads chunk JSONL
- Embeds chunks
- Upserts into `rag_documents` and `rag_chunks`
- Reports stats (`inserted/updated/skipped/failures`)

### `tools/rag/smoke.py`
Responsibility:
- Counts vector tables
- Runs sample retrieval query
- Prints structured smoke output

### `tools/rag/main.py` and `tools/rag/__main__.py`
Responsibility:
- CLI entrypoint and subcommand argument parsing for `migrate`, `load`, `smoke`

## 7) Configuration & Environment Variables

RAG-related variables in `app/settings.py`:

- `RAG_ENABLED`
  - Enables router mounting and endpoint availability for RAG admin routes.

- `OLLAMA_BASE_URL`
  - Base URL for embedding/chat HTTP calls.
  - Must be reachable from app runtime environment.

- `OLLAMA_EMBED_MODEL`
  - Embedding model name sent to Ollama `/api/embeddings`.

- `OLLAMA_CHAT_MODEL`
  - Chat model name sent to Ollama `/api/chat`.

- `RAG_EMBED_DIM`
  - Expected embedding length in code-level validation.
  - Must match DB vector dimension.

- `RAG_TOP_K`
  - Default retrieval candidate count before score filtering.

- `RAG_MIN_SCORE`
  - Post-query threshold; matches below threshold are dropped.

- `RAG_MAX_CONTEXT_CHARS`
  - Upper bound for assembled context length sent to LLM.

- `RAG_CHUNKS_PATH`
  - Input file path for loader (`python -m tools.rag load`).

- `RAG_BATCH_SIZE`
  - Chunk batch size for embed+upsert flush cycles in loader.

Observed values in repo files:
- `.env`:
  - `RAG_ENABLED=true`, `RAG_MIN_SCORE=0.0`, `RAG_BATCH_SIZE=64`
- `.env.production`:
  - `RAG_ENABLED=true`, `RAG_MIN_SCORE=0.2`
- `.env.production.example`:
  - `RAG_ENABLED=false`

## 8) Security Model

### Why RAG is admin-only
- RAG routes exist only under `/admin/rag/*`
- Both endpoints require valid `X-API-Key`
- Router is only mounted when `RAG_ENABLED=true`

### How feature flag isolates it
- `app/main.py` conditionally includes RAG router only when enabled
- `app/rag/admin_routes.py` also checks enabled state and returns `404` if disabled

### X-API-Key protection
- Route receives `X-API-Key` header
- `require_admin` compares against `settings.admin_api_key`
- Failure returns `401 Unauthorized`

### What prevents public exposure
Current protections:
- No public route path for RAG
- Admin API key requirement
- Optional full disable via `RAG_ENABLED=false`

### Risks if exposed without gating
- Prompt injection and data exfiltration risk from arbitrary users
- Cost/latency amplification via open embedding + generation endpoints
- Potential leakage of internal source corpus and scoring metadata
- Increased abuse surface on Ollama and Postgres

## 9) Dependencies & Exact Versions

Extracted directly from repository files:

Python/runtime:
- Python image: `python:3.11-slim` (`docker/Dockerfile`)

Core Python packages (`requirements.txt`):
- `fastapi==0.115.0`
- `uvicorn[standard]==0.30.6`
- `pydantic==2.8.2`
- `python-dotenv==1.0.1`
- `httpx==0.27.2`
- `beautifulsoup4==4.12.3`
- `trafilatura==1.12.2`
- `lxml==5.3.0`
- `tldextract==5.1.2`
- `tenacity==9.0.0`
- `redis==5.0.8`
- `psycopg[binary]==3.2.1`
- `sendgrid==6.11.0`

Infrastructure images:
- PostgreSQL + pgvector image: `pgvector/pgvector:pg16`
- Redis image: `redis:7`
- Nginx image: `nginx:alpine`

Ollama models (configured names):
- Embedding: `nomic-embed-text`
- Chat: `llama3.1:8b`

Note on pgvector extension version:
- The repository pins the container image tag (`pgvector/pgvector:pg16`) but does not explicitly pin/report extension semantic version in code.

## 10) Deployment Flow (Dev & Prod)

### Local flow
1. Configure `.env` (current file enables RAG and points Ollama to `host.docker.internal:11434`).
2. Start stack:
```bash
docker compose up -d --build
```
3. Ensure Ollama is running and models are pulled on host/target.
4. Apply RAG schema:
```bash
python -m tools.rag migrate
```
5. Load embeddings:
```bash
python -m tools.rag load
```
6. Smoke retrieval:
```bash
python -m tools.rag smoke --query "What villa projects do you have?" --top-k 5
```
7. Test admin RAG endpoints with `X-API-Key`.

### Production flow
Primary compose file: `docker-compose.prod.yml`.

Steps:
1. Prepare `.env.production` with real secrets and DSNs.
2. Deploy:
```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```
3. Verify service health and logs.
4. If RAG required in prod, ensure:
   - `RAG_ENABLED=true`
   - Ollama endpoint reachable from `app` container runtime
   - RAG migration and load completed against production DB

Database persistence:
- Uses named Docker volume `pgdata:/var/lib/postgresql/data`.

Backup strategy (current-state assessment + practical ops guidance):
- Persistence exists via Docker volume; automated backup workflow is not implemented in repo code.
- Operationally, backups should be externalized (e.g., `pg_dump` scheduled jobs + volume snapshots).

Scaling considerations:
- Horizontal `app` scaling requires shared Redis/Postgres (already externalized by services).
- Worker can be scaled with queue contention handled by `FOR UPDATE SKIP LOCKED`.
- RAG retrieval scales with DB/index tuning and Ollama capacity; Ollama is currently a single external dependency endpoint.

## 11) File Modification Guide (No Logic Changes Applied)

If you want to change behavior, these are the exact files/knobs to update.

### Change embedding model
- Env: `OLLAMA_EMBED_MODEL` in `.env` / `.env.production`
- Validation dim: `RAG_EMBED_DIM` in env
- If dimension changes: update `tools/rag/sql/001_pgvector_schema.sql` (`VECTOR(...)`) and re-embed

### Change LLM model
- Env: `OLLAMA_CHAT_MODEL` in `.env` / `.env.production`

### Adjust similarity threshold
- Env: `RAG_MIN_SCORE`
- Retrieval filter implemented in `app/rag/retriever.py`

### Increase performance
- Retrieval/context knobs: `RAG_TOP_K`, `RAG_MIN_SCORE`, `RAG_MAX_CONTEXT_CHARS`
- Loader throughput knob: `RAG_BATCH_SIZE`
- Vector index shape: `tools/rag/sql/001_pgvector_schema.sql` (IVFFlat `lists`)
- Embed call behavior currently in `app/rag/embedder.py` (serial calls)

### Move from Ollama to OpenAI
Files to adapt:
- `app/rag/ollama_client.py` (provider client + response parsing)
- `app/rag/embedder.py` (embedding call contract)
- `app/rag/rag_answer.py` (chat call target client)
- `app/settings.py` + env templates for new provider keys/base URLs/models
- Tests: `tests/test_ollama_response_parsing.py` (and add provider-specific tests)

### Change vector dimension
- `tools/rag/sql/001_pgvector_schema.sql` (`VECTOR(768)`)
- `RAG_EMBED_DIM` in env
- Reinitialize/rebuild schema and re-embed corpus

### Add new document sources
- Scraper/discovery logic: `tools/ingestion/scrape_site.py`
- Extraction rules: `tools/ingestion/extract_text.py`
- Chunking behavior: `tools/ingestion/chunk_docs.py`
- Then rerun ingestion + embedding load

### Re-embed all data
- Command: `python -m tools.rag load --reembed`
- Source file path: `RAG_CHUNKS_PATH`

### Disable RAG
- Set `RAG_ENABLED=false` in target env
- RAG admin router will not mount

### Integrate RAG into public chat
- Current public chat flow is in `app/bot/state_machine.py` and `/chat/message` handler in `app/main.py`
- Integration requires explicit code path from chat flow to `answer_with_rag` with suitable safeguards

### Scale horizontally
- Compose/service level changes in `docker-compose*.yml`
- Ensure shared state services (Redis/Postgres) remain centralized
- Review nginx upstream/load-balancing strategy in `docker/nginx.conf` if multiple app replicas are introduced

## 12) Current Status & Next Phase

### What is complete
- Full ingestion-to-vector pipeline exists (Phases 1/2 + Phase 3 tooling)
- pgvector schema, embedding loader, retrieval, and answer generation implemented
- Admin-only API exposure and feature-flag gating implemented

### What is stable
- Core non-RAG production stack (chat, leads, analytics, worker, webhook) is integrated and documented
- RAG code paths have supporting tests for SQL/result shape and Ollama response parsing

### What is experimental or operationally sensitive
- Ollama dependency is external to compose and may vary by deployment
- RAG retrieval/answer quality depends on corpus freshness, model behavior, and threshold tuning
- Migration system for RAG is single-file SQL, not a full migration history framework

### Recommended next architectural step
- Introduce formal migration/versioning for RAG schema evolution and model/dimension transitions.
- Add production-grade RAG observability: retrieval hit-rate, score distribution, latency, and answer quality feedback loop.

### Risks before exposing RAG publicly
- Abuse risk without stronger auth/rate limits
- Hallucination risk if threshold/context controls are too permissive
- Operational bottlenecks at Ollama endpoint
- Data exposure risk if source metadata/chunks are returned without policy controls
