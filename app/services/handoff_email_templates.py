from datetime import datetime, timezone
from html import escape


def _to_dash(value) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text else "-"


def _format_created_at(value) -> str:
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return _to_dash(value)


def build_subject(conversation_id: str) -> str:
    short = conversation_id[-8:] if conversation_id else "-"
    return f"OBE Architects | WhatsApp Handoff Request #{short}"


def build_body_text(details: dict) -> str:
    return (
        "----------------------------------------\n"
        "HANDOFF REQUESTED\n"
        f"Conversation ID: {_to_dash(details.get('conversation_id'))}\n"
        f"Created: {_format_created_at(details.get('created_at'))}\n\n"
        "Customer\n"
        f"- Channel: {_to_dash(details.get('channel'))}\n"
        f"- External User ID: {_to_dash(details.get('external_user_id'))}\n"
        f"- Last Message: {_to_dash(details.get('last_message'))}\n"
        "----------------------------------------"
    )


def build_body_html(details: dict) -> str:
    return f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f3f6fb;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
      Handoff requested on WhatsApp.
    </div>
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f3f6fb;padding:24px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="620" style="max-width:620px;width:100%;background:#ffffff;border:1px solid #d8e2f0;border-radius:12px;overflow:hidden;">
            <tr>
              <td style="padding:18px 24px;background:linear-gradient(135deg,#0f6fb5,#1a8ca3);color:#ffffff;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;">
                <div style="font-size:18px;font-weight:700;line-height:1.3;">Handoff Requested</div>
                <div style="margin-top:6px;font-size:13px;opacity:0.92;">Conversation ID: {escape(_to_dash(details.get('conversation_id')))}</div>
                <div style="margin-top:2px;font-size:12px;opacity:0.86;">Created: {escape(_format_created_at(details.get('created_at')))}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 24px;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;color:#1d2a3b;">
                <div style="font-size:13px;font-weight:700;letter-spacing:0.4px;text-transform:uppercase;color:#57708f;margin-bottom:10px;">Customer Details</div>
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
                  <tr><td style="padding:8px 0;width:170px;font-size:13px;color:#5b6f88;">Channel</td><td style="padding:8px 0;font-size:14px;font-weight:600;">{escape(_to_dash(details.get('channel')))}</td></tr>
                  <tr><td style="padding:8px 0;width:170px;font-size:13px;color:#5b6f88;">External User ID</td><td style="padding:8px 0;font-size:14px;font-weight:600;">{escape(_to_dash(details.get('external_user_id')))}</td></tr>
                  <tr><td style="padding:8px 0;width:170px;font-size:13px;color:#5b6f88;">Last Message</td><td style="padding:8px 0;font-size:14px;font-weight:600;">{escape(_to_dash(details.get('last_message')))}</td></tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:14px 24px;background:#f7f9fd;border-top:1px solid #d8e2f0;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;color:#67809b;font-size:12px;">
                OBE Architects Bot · Automated handoff notification
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""".strip()
