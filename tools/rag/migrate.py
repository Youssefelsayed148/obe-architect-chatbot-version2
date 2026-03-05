from __future__ import annotations

from pathlib import Path

from psycopg import connect

from app.settings import settings


def run_migration(sql_path: str | Path | None = None) -> dict:
    path = Path(sql_path) if sql_path else Path(__file__).resolve().parent / "sql" / "001_pgvector_schema.sql"
    sql = path.read_text(encoding="utf-8")
    with connect(settings.postgres_dsn) as con:
        con.execute(sql)
        con.commit()
    return {"ok": True, "sql_path": str(path)}
