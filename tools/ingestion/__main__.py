from __future__ import annotations

import argparse
from pathlib import Path

from app.settings import settings
from tools.ingestion.chunk_docs import chunk_documents, smoke_validate_chunks
from tools.ingestion.scrape_site import run_scrape


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OBE ingestion tools (Phase 0/1/2)")
    sub = parser.add_subparsers(dest="command", required=True)

    scrape_cmd = sub.add_parser("scrape", help="Run website scrape and extraction")
    scrape_cmd.add_argument("--output-dir", default=settings.scrape_output_dir)
    scrape_cmd.add_argument("--max-pages", type=int, default=settings.scrape_max_pages)
    scrape_cmd.add_argument("--rps", type=float, default=settings.scrape_rps)

    chunk_cmd = sub.add_parser("chunk", help="Clean and chunk scraped documents")
    chunk_cmd.add_argument(
        "--input",
        default=str(Path(settings.scrape_output_dir) / "cleaned" / "documents.jsonl"),
    )
    chunk_cmd.add_argument(
        "--output",
        default=str(Path(settings.scrape_output_dir) / "chunks" / "chunks.jsonl"),
    )
    chunk_cmd.add_argument("--chunk-size-chars", type=int, default=3200)
    chunk_cmd.add_argument("--overlap-chars", type=int, default=250)

    smoke_cmd = sub.add_parser("smoke", help="Print simple ingestion stats")
    smoke_cmd.add_argument(
        "--docs",
        default=str(Path(settings.scrape_output_dir) / "cleaned" / "documents.jsonl"),
    )
    smoke_cmd.add_argument(
        "--chunks",
        default=str(Path(settings.scrape_output_dir) / "chunks" / "chunks.jsonl"),
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "scrape":
        result = run_scrape(output_dir=args.output_dir, max_pages=args.max_pages, rps=args.rps)
        print(result)
        return
    if args.command == "chunk":
        result = chunk_documents(
            input_path=args.input,
            output_path=args.output,
            chunk_size_chars=args.chunk_size_chars,
            overlap_chars=args.overlap_chars,
        )
        print(result)
        return
    if args.command == "smoke":
        smoke_validate_chunks(docs_path=args.docs, chunks_path=args.chunks)
        return
    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
