import logging
import time

from app.store.postgres import (
    claim_pending_email_outbox,
    init_db,
    mark_email_outbox_failure,
    mark_email_outbox_sent,
)
from app.services.email_sender import send_email


logger = logging.getLogger(__name__)


def process_once(limit: int = 10) -> int:
    rows = claim_pending_email_outbox(limit=limit)
    for row in rows:
        outbox_id = int(row["id"])
        lead_id = int(row["lead_id"]) if row.get("lead_id") is not None else None
        to_email = row["to_email"]
        attempts = int(row["attempts"])
        event_type = row.get("event_type", "lead")
        try:
            send_email(
                to_email=to_email,
                subject=row["subject"],
                body_text=row["body_text"],
                body_html=row.get("body_html"),
            )
            mark_email_outbox_sent(outbox_id)
            logger.info(
                "email_outbox processed outbox_id=%s lead_id=%s event_type=%s to_email=%s attempts=%s status=sent",
                outbox_id,
                lead_id,
                event_type,
                to_email,
                attempts,
            )
        except Exception as exc:
            error = str(exc)
            mark_email_outbox_failure(outbox_id, error)
            status = "failed" if attempts >= 8 else "pending"
            logger.error(
                "email_outbox processed outbox_id=%s lead_id=%s event_type=%s to_email=%s attempts=%s status=%s error=%s",
                outbox_id,
                lead_id,
                event_type,
                to_email,
                attempts,
                status,
                error,
            )
    return len(rows)


def run_forever(poll_seconds: int = 2, batch_size: int = 10) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logger.info("email worker started poll_seconds=%s batch_size=%s", poll_seconds, batch_size)
    init_db()
    while True:
        try:
            processed = process_once(limit=batch_size)
            if processed == 0:
                time.sleep(poll_seconds)
        except Exception:
            logger.exception("email worker loop failed")
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run_forever()

