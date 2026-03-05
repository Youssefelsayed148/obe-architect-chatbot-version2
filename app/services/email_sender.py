import logging

from app.settings import settings

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    if not settings.sendgrid_api_key or not settings.email_from:
        if settings.app_env != "production":
            logger.info(
                "Email send skipped (missing SendGrid config) app_env=%s to=%s",
                settings.app_env,
                to_email,
            )
            return
        if not settings.sendgrid_api_key:
            raise RuntimeError("SENDGRID_API_KEY is not configured")
        raise RuntimeError("EMAIL_FROM is not configured")

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    msg = Mail(
        from_email=settings.email_from,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body_text,
        html_content=body_html if body_html else None,
    )

    client = SendGridAPIClient(settings.sendgrid_api_key)
    resp = client.send(msg)
    if resp.status_code >= 400:
        body = ""
        if hasattr(resp, "body") and resp.body is not None:
            body = resp.body.decode("utf-8", errors="replace") if isinstance(resp.body, bytes) else str(resp.body)
        raise RuntimeError(f"SendGrid API failed with status={resp.status_code} body={body}")
