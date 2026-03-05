def test_email_worker_marks_sent_on_success(monkeypatch):
    from app.worker import email_worker

    monkeypatch.setattr(
        email_worker,
        "claim_pending_email_outbox",
        lambda limit=10: [
            {
                "id": 11,
                "lead_id": 101,
                "to_email": "jojgame10@gmail.com",
                "subject": "s",
                "body_text": "t",
                "body_html": "<p>t</p>",
                "attempts": 1,
            }
        ],
    )

    calls = {"send": 0, "sent": [], "failed": []}

    def fake_send_email(**kwargs):
        calls["send"] += 1

    monkeypatch.setattr(email_worker, "send_email", fake_send_email)
    monkeypatch.setattr(email_worker, "mark_email_outbox_sent", lambda outbox_id: calls["sent"].append(outbox_id))
    monkeypatch.setattr(
        email_worker,
        "mark_email_outbox_failure",
        lambda outbox_id, error: calls["failed"].append((outbox_id, error)),
    )

    processed = email_worker.process_once(limit=10)

    assert processed == 1
    assert calls["send"] == 1
    assert calls["sent"] == [11]
    assert calls["failed"] == []


def test_email_worker_retries_and_marks_failed_after_8_attempts(monkeypatch):
    from app.worker import email_worker

    monkeypatch.setattr(
        email_worker,
        "claim_pending_email_outbox",
        lambda limit=10: [
            {
                "id": 12,
                "lead_id": 102,
                "to_email": "jojgame10@gmail.com",
                "subject": "s",
                "body_text": "t",
                "body_html": None,
                "attempts": 8,
            }
        ],
    )

    def failing_send_email(**kwargs):
        raise RuntimeError("sendgrid down")

    monkeypatch.setattr(email_worker, "send_email", failing_send_email)

    calls = {"sent": [], "failed": []}
    monkeypatch.setattr(email_worker, "mark_email_outbox_sent", lambda outbox_id: calls["sent"].append(outbox_id))
    monkeypatch.setattr(
        email_worker,
        "mark_email_outbox_failure",
        lambda outbox_id, error: calls["failed"].append((outbox_id, error)),
    )

    processed = email_worker.process_once(limit=10)

    assert processed == 1
    assert calls["sent"] == []
    assert calls["failed"]
    assert calls["failed"][0][0] == 12
    assert "sendgrid down" in calls["failed"][0][1]

