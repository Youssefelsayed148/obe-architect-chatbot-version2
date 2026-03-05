from __future__ import annotations

import json
import warnings
from pathlib import Path


COMMON_CHUNKS_PATHS = (
    Path("data/ingestion/chunks/chunks.jsonl"),
    Path("data/chunks/chunks.jsonl"),
    Path("chunks/chunks.jsonl"),
)

REQUIRED_KEYS = {"url", "title", "chunk_text", "chunk_index"}
NOISE_TOKENS = (
    "privacy",
    "terms",
    "cookies",
    "all rights reserved",
    "copyright",
    "contact us",
    "follow us",
    "menu",
    "home",
)


def _discover_chunks_path() -> Path | None:
    for path in COMMON_CHUNKS_PATHS:
        if path.exists():
            return path
    for path in Path(".").glob("**/chunks.jsonl"):
        if path.is_file():
            return path
    return None


def test_chunks_jsonl_schema_and_quality():
    chunks_path = _discover_chunks_path()
    assert chunks_path is not None, f"chunks.jsonl not found in common paths: {COMMON_CHUNKS_PATHS}"

    rows: list[dict] = []
    with chunks_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    assert rows, f"chunks file is empty: {chunks_path}"

    missing_schema_rows = 0
    non_empty = 0
    lengths: list[int] = []
    for row in rows:
        if not REQUIRED_KEYS.issubset(set(row.keys())):
            missing_schema_rows += 1
        chunk_text = str(row.get("chunk_text", "")).strip()
        if chunk_text:
            non_empty += 1
            lengths.append(len(chunk_text))

    non_empty_ratio = non_empty / len(rows)
    avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0
    print(
        "ingestion_chunks_summary "
        f"path={chunks_path} rows={len(rows)} non_empty_ratio={non_empty_ratio:.4f} avg_len={avg_len:.2f}"
    )

    assert missing_schema_rows == 0, f"schema violations in {missing_schema_rows} rows"
    assert non_empty_ratio >= 0.99, f"non-empty chunk_text ratio below threshold: {non_empty_ratio:.4f}"


def test_chunks_noise_heuristic_warn_unless_extreme():
    chunks_path = _discover_chunks_path()
    assert chunks_path is not None, f"chunks.jsonl not found in common paths: {COMMON_CHUNKS_PATHS}"

    sample: list[str] = []
    with chunks_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if len(sample) >= 20:
                break
            line = line.strip()
            if not line:
                continue
            sample.append(str(json.loads(line).get("chunk_text", "")))

    assert sample, f"unable to sample chunk_text from {chunks_path}"

    noisy = 0
    for text in sample:
        lower = text.lower()
        token_hits = sum(1 for token in NOISE_TOKENS if token in lower)
        if token_hits >= 4:
            noisy += 1

    noisy_ratio = noisy / len(sample)
    print(f"ingestion_chunks_noise sampled={len(sample)} noisy={noisy} noisy_ratio={noisy_ratio:.2f}")

    if noisy_ratio >= 0.25:
        warnings.warn(
            f"Chunk sample contains notable nav/footer noise (noisy_ratio={noisy_ratio:.2f})",
            stacklevel=1,
        )

    assert noisy_ratio < 0.75, f"extreme nav/footer noise detected in chunks sample: {noisy_ratio:.2f}"
