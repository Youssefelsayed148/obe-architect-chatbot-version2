from __future__ import annotations

import argparse

from app.settings import settings
from tools.rag.load_embeddings import load_embeddings
from tools.rag.migrate import run_migration
from tools.rag.smoke import run_smoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OBE RAG tools (Phase 3)")
    sub = parser.add_subparsers(dest="command", required=True)

    migrate_cmd = sub.add_parser("migrate", help="Apply pgvector schema migration")
    migrate_cmd.add_argument("--sql-path", default=None)

    load_cmd = sub.add_parser("load", help="Embed and load chunks into pgvector")
    load_cmd.add_argument("--chunks-path", default=settings.rag_chunks_path)
    load_cmd.add_argument("--limit", type=int, default=None)
    load_cmd.add_argument("--reembed", action="store_true")
    load_cmd.add_argument("--batch-size", type=int, default=settings.rag_batch_size)

    smoke_cmd = sub.add_parser("smoke", help="Show vector-table counts and sample search")
    smoke_cmd.add_argument("--query", default="OBE architects projects")
    smoke_cmd.add_argument("--top-k", type=int, default=3)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "migrate":
        print(run_migration(sql_path=args.sql_path))
        return
    if args.command == "load":
        print(
            load_embeddings(
                chunks_path=args.chunks_path,
                limit=args.limit,
                reembed=args.reembed,
                batch_size=args.batch_size,
            )
        )
        return
    if args.command == "smoke":
        run_smoke(query=args.query, top_k=args.top_k)
        return
    parser.error(f"Unknown command: {args.command}")
