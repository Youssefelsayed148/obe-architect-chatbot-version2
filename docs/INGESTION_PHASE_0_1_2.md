# Ingestion Phase 0/1/2

This document covers the implemented ingestion foundation for RAG preparation without embeddings.

## Scope

- Phase 0: safety/operational config, output boundaries, and runbook commands.
- Phase 1: website scraping + text extraction for OBE site section (`/obe/`).
- Phase 2: cleaning + character chunking for downstream embedding in a later phase.

No existing chat, lead, analytics, email, or widget behavior is modified by these tools.

## Configuration (Phase 0)

Environment variables (defaults):

- `SCRAPE_BASE_URL=https://obearchitects.com/obe/`
- `SCRAPE_START_URL=https://obearchitects.com/obe/index.php`
- `SCRAPE_RPS=1.0`
- `SCRAPE_MAX_PAGES=2000`
- `SCRAPE_OUTPUT_DIR=data/ingestion`
- `SCRAPE_USER_AGENT=OBE-RAG-Ingestion/1.0 (+contact: info@obearchitects.com)`
- `SCRAPE_ALLOW_SUBDOMAINS=false`
- `SCRAPE_RESPECT_ROBOTS=true`
- `SCRAPE_PATH_PREFIX=/obe/`
- `SCRAPE_ALLOWED_QUERY_KEYS=category,id`

## Commands

Install dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Run Phase 1 scrape:

```bash
python -m tools.ingestion scrape
```

Optional flags:

```bash
python -m tools.ingestion scrape --max-pages 500 --rps 0.5 --output-dir data/ingestion
```

Run Phase 2 chunking:

```bash
python -m tools.ingestion chunk
```

Optional flags:

```bash
python -m tools.ingestion chunk --chunk-size-chars 3200 --overlap-chars 250
```

Smoke validation:

```bash
python -m tools.ingestion smoke
```

Inside Docker app container:

```bash
docker compose exec app python -m tools.ingestion scrape
docker compose exec app python -m tools.ingestion chunk
docker compose exec app python -m tools.ingestion smoke
```

## Output Locations

- Cleaned documents JSONL:
  - `data/ingestion/cleaned/documents.jsonl`
- Crawl report per run:
  - `data/ingestion/reports/run_<timestamp>.json`
- Chunked JSONL:
  - `data/ingestion/chunks/chunks.jsonl`

## Quick Validation Checklist

1. Confirm `documents.jsonl` exists and has non-empty `text` values.
2. Confirm report contains category and project-detail counts plus structured discovery counts:
   - `discovered_categories_count`
   - `discovered_project_ids_count`
   - `category_pages_fetched_count`
   - `project_detail_pages_fetched_count`
3. Run smoke command and review:
   - `docs_count`, `chunks_count`
   - top domains
   - 3 chunk previews with source URLs

## Phase 1 Discovery Strategy (OBE)

For `obearchitects.com`, scraping uses a structured mode by default:

1. Category discovery:
   - Fetches hub pages:
     - `https://obearchitects.com/obe/projects.php`
     - `https://obearchitects.com/obe/index.php`
   - Extracts category slugs via regex:
     - `projectlists.php?category=<slug>`
2. Project ID discovery:
   - Fetches each category page:
     - `https://obearchitects.com/obe/projectlists.php?category=<slug>`
   - Extracts project IDs via regex:
     - `project-detail.php?id=<id>`
3. Detail scraping:
   - Fetches each unique project detail URL:
     - `https://obearchitects.com/obe/project-detail.php?id=<id>`
   - Also scrapes fixed core non-project pages (`expertise`, `media`, `about-us`, `contact-us`, etc.)

Fallback behavior:
- If categories or project IDs are not discovered, scraper falls back to bounded BFS crawl within scope.

## Safety Disclaimer

Respect `robots.txt` and keep request rate conservative (`SCRAPE_RPS`) to avoid operational impact on source infrastructure. By default, ingestion stops if robots.txt cannot be fetched while `SCRAPE_RESPECT_ROBOTS=true`.
