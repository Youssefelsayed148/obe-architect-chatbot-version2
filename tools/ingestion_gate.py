from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

REQUIRED_KEYS = {"url", "chunk_text"}
OPTIONAL_KEYS = {"title", "chunk_index"}
NAV_FOOTER_TOKENS = (
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


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                yield line_no, json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_no}: {exc}") from exc


def nav_footer_score(text: str) -> int:
    lower = text.lower()
    return sum(1 for token in NAV_FOOTER_TOKENS if token in lower)


def run(chunks_path: Path, sample_size: int = 10) -> int:
    if not chunks_path.exists():
        print(f"FAIL: chunks file not found: {chunks_path}")
        return 1

    total = 0
    missing_required = 0
    empty_text = 0
    lens: list[int] = []
    domain_counts: Counter[str] = Counter()
    samples: list[tuple[str, str]] = []

    for line_no, row in iter_jsonl(chunks_path):
        total += 1
        if not isinstance(row, dict):
            print(f"FAIL: row {line_no} is not an object")
            return 1

        row_keys = set(row.keys())
        if not REQUIRED_KEYS.issubset(row_keys):
            missing_required += 1

        text = str(row.get("chunk_text") or "").strip()
        if not text:
            empty_text += 1
        else:
            lens.append(len(text))

        url = str(row.get("url") or "").strip()
        if url:
            domain_counts[urlparse(url).netloc] += 1

        if len(samples) < sample_size:
            samples.append((url, text))

    if total == 0:
        print("FAIL: chunks file is empty")
        return 1

    non_empty_ratio = (total - empty_text) / total
    avg_len = (sum(lens) / len(lens)) if lens else 0.0
    min_len = min(lens) if lens else 0
    max_len = max(lens) if lens else 0

    nav_hits = []
    for idx, (url, text) in enumerate(samples, start=1):
        score = nav_footer_score(text)
        nav_hits.append({"sample": idx, "url": url, "token_hits": score, "preview": text[:160].replace("\n", " ")})

    nav_dominated = [x for x in nav_hits if x["token_hits"] >= 4]

    print(json.dumps(
        {
            "chunks_path": str(chunks_path),
            "rows_total": total,
            "missing_required_rows": missing_required,
            "optional_keys_considered": sorted(OPTIONAL_KEYS),
            "non_empty_chunk_text_ratio": round(non_empty_ratio, 6),
            "length": {
                "avg": round(avg_len, 2),
                "min": min_len,
                "max": max_len,
            },
            "top_10_domains": domain_counts.most_common(10),
            "sample_nav_footer_heuristic": nav_hits,
            "nav_footer_dominated_samples": len(nav_dominated),
        },
        indent=2,
        ensure_ascii=False,
    ))

    passed = True
    if missing_required > 0:
        print(f"FAIL: {missing_required} rows missing required keys {sorted(REQUIRED_KEYS)}")
        passed = False
    if non_empty_ratio < 0.99:
        print(f"FAIL: non-empty chunk_text ratio {non_empty_ratio:.4f} < 0.99")
        passed = False
    if nav_dominated:
        print("FAIL: navigation/footer token dominance detected in sample set")
        passed = False

    if passed:
        print("PASS: ingestion gate checks passed")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0/1/2 ingestion artifact gate checks")
    parser.add_argument("--chunks", default="data/ingestion/chunks/chunks.jsonl")
    parser.add_argument("--sample-size", type=int, default=10)
    args = parser.parse_args()
    return run(Path(args.chunks), sample_size=args.sample_size)


if __name__ == "__main__":
    raise SystemExit(main())
