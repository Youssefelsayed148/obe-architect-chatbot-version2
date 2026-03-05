import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.store import postgres


@pytest.mark.integration
def test_postgres_store_roundtrip(monkeypatch):
    dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        pytest.skip("POSTGRES_DSN is not set; skipping integration test.")

    monkeypatch.setattr(postgres.settings, "postgres_dsn", dsn)

    postgres.init_db()

    session_id = f"it_{uuid.uuid4().hex[:12]}"
    postgres.insert_lead(
        name="Integration Test",
        phone="+15551234567",
        email="integration@example.com",
        project_type="Villa",
        message="integration check",
        source="web",
        session_id=session_id,
    )

    rows = postgres.list_leads(limit=200)
    assert any(r["session_id"] == session_id for r in rows)


@pytest.mark.integration
def test_postgres_click_aggregation_by_department(monkeypatch):
    dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        pytest.skip("POSTGRES_DSN is not set; skipping integration test.")

    monkeypatch.setattr(postgres.settings, "postgres_dsn", dsn)
    postgres.init_db()

    unique = uuid.uuid4().hex[:8]
    dept_a = f"IT_{unique}_A"
    dept_b = f"IT_{unique}_B"

    window_start = datetime.now(timezone.utc) - timedelta(minutes=1)
    postgres.insert_analytics_event(
        event_name="project_category_click",
        category=dept_a,
        department=dept_a,
        url="https://example.test/a",
        session_id=f"it_{unique}",
        user_id=f"user_{unique}",
        source="integration",
        route_taken=None,
        retrieval_top_score=None,
        retrieval_k=None,
        fallback_reason=None,
    )
    postgres.insert_analytics_event(
        event_name="project_category_click",
        category=dept_a,
        department=dept_a,
        url="https://example.test/a2",
        session_id=f"it_{unique}",
        user_id=f"user_{unique}",
        source="integration",
        route_taken=None,
        retrieval_top_score=None,
        retrieval_k=None,
        fallback_reason=None,
    )
    postgres.insert_analytics_event(
        event_name="project_category_click",
        category=dept_b,
        department=dept_b,
        url="https://example.test/b",
        session_id=f"it_{unique}",
        user_id=f"user_{unique}",
        source="integration",
        route_taken=None,
        retrieval_top_score=None,
        retrieval_k=None,
        fallback_reason=None,
    )
    postgres.insert_analytics_event(
        event_name="project_category_click",
        category=None,
        department=None,
        url="https://example.test/u",
        session_id=f"it_{unique}",
        user_id=f"user_{unique}",
        source="integration",
        route_taken=None,
        retrieval_top_score=None,
        retrieval_k=None,
        fallback_reason=None,
    )
    window_end = datetime.now(timezone.utc) + timedelta(minutes=1)

    rows = postgres.get_click_counts_by_department(start=window_start, end=window_end)
    counts = {row["department"]: int(row["clicks"]) for row in rows}

    assert counts[dept_a] == 2
    assert counts[dept_b] == 1
    assert counts["unknown"] >= 1


@pytest.mark.integration
def test_consultation_lead_enqueue_outbox_once(monkeypatch):
    dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        pytest.skip("POSTGRES_DSN is not set; skipping integration test.")

    monkeypatch.setattr(postgres.settings, "postgres_dsn", dsn)
    postgres.init_db()

    unique = uuid.uuid4().hex[:10]
    lead_id = postgres.insert_consultation_lead_and_enqueue_email(
        name=f"Lead {unique}",
        phone="+15550001111",
        email=f"{unique}@example.com",
        consultant_type="Architecture",
        source="integration",
        session_id=f"s_{unique}",
        notify_to="jojgame10@gmail.com",
    )

    from psycopg import connect
    from psycopg.rows import dict_row

    with connect(dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT event_key, lead_id, to_email, status FROM email_outbox WHERE event_key=%s", (f"lead_notify:{lead_id}",))
            rows = cur.fetchall()

    assert len(rows) == 1
    assert rows[0]["lead_id"] == lead_id
    assert rows[0]["to_email"] == "jojgame10@gmail.com"
    assert rows[0]["status"] == "pending"


@pytest.mark.integration
def test_email_outbox_claim_increments_attempts_and_fails_on_attempt_8(monkeypatch):
    dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        pytest.skip("POSTGRES_DSN is not set; skipping integration test.")

    monkeypatch.setattr(postgres.settings, "postgres_dsn", dsn)
    postgres.init_db()

    unique = uuid.uuid4().hex[:10]
    lead_id = postgres.insert_consultation_lead_and_enqueue_email(
        name=f"Lead {unique}",
        phone="+15550002222",
        email=f"{unique}@example.com",
        consultant_type="Architecture",
        source="integration",
        session_id=f"s_{unique}",
        notify_to="jojgame10@gmail.com",
    )

    from psycopg import connect
    from psycopg.rows import dict_row

    event_key = f"lead_notify:{lead_id}"
    with connect(dsn) as con:
        con.execute("UPDATE email_outbox SET attempts=7 WHERE event_key=%s", (event_key,))
        con.commit()

    claimed = postgres.claim_pending_email_outbox(limit=10)
    claimed_row = next(r for r in claimed if r["lead_id"] == lead_id)
    assert int(claimed_row["attempts"]) == 8

    postgres.mark_email_outbox_failure(int(claimed_row["id"]), "final failure")

    with connect(dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT attempts, status, last_error FROM email_outbox WHERE event_key=%s", (event_key,))
            row = cur.fetchone()

    assert int(row["attempts"]) == 8
    assert row["status"] == "failed"
    assert "final failure" in (row["last_error"] or "")
