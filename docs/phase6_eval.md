# Phase 6 Evaluation and Tests

## Scope
- Golden dataset for retrieval/refusal regression checks.
- Chunk artifact quality checks (Phase 0/1/2).
- Retrieval URL checks against golden set (Phase 3).
- Refusal contract checks for public RAG endpoint payloads (Phase 4).

## Run
```bash
python -m pytest -q
```

Optional: run integration-only retrieval checks explicitly.
```bash
python -m pytest -q -m integration tests/test_retrieval_golden.py
```

## Golden Set
- File: `tests/golden/golden_questions.jsonl`
- JSONL fields per row:
  - `id`: stable identifier.
  - `lang`: `en` or `ar`.
  - `question`: user question text.
  - `expected_urls`: URLs expected in retrieval for answerable items.
  - `must_refuse`: whether answer should be fallback refusal.
  - `notes` (optional): rationale/category.

### Add New Golden Questions
1. Append a new JSON line to `tests/golden/golden_questions.jsonl`.
2. For answerable entries (`must_refuse=false`), include at least one valid URL in `expected_urls`.
3. Keep refusal entries (`must_refuse=true`) with empty `expected_urls`.
4. Keep overall dataset balanced across services/process/project types.

## Metrics Interpretation
- `tests/test_ingestion_chunks.py`
  - Validates chunk file exists and schema quality.
  - Requires `chunk_text` non-empty ratio >= 99%.
  - Emits warning for moderate nav/footer noise; fails only on extreme noise.
- `tests/test_retrieval_golden.py`
  - For each answerable golden entry (English subset), asserts at least one expected URL appears in top-k retrieval output.
  - `top_k` is read from `RAG_PUBLIC_TOP_K` (default 5).
  - Test is marked `integration` and skips if Postgres/RAG tables are unavailable.
- `tests/test_rag_refusal.py`
  - For each refusal golden entry, verifies `/chat/ask` returns fallback wording, empty sources, and confidence below threshold.
