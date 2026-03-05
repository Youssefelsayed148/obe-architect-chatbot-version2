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


def _lead_fields(lead: dict) -> dict:
    consultant_type = lead.get("consultant_type")
    if consultant_type is None:
        consultant_type = lead.get("project_type")

    return {
        "id": _to_dash(lead.get("id")),
        "created_at": _format_created_at(lead.get("created_at")),
        "name": _to_dash(lead.get("name")),
        "email": _to_dash(lead.get("email")),
        "phone": _to_dash(lead.get("phone")),
        "consultant_type": _to_dash(consultant_type),
        "source": _to_dash(lead.get("source")),
        "session_id": _to_dash(lead.get("session_id")),
    }


def build_subject(lead_id: str) -> str:
    lead_id_text = _to_dash(lead_id)
    short = lead_id_text[-8:] if lead_id_text != "-" else "-"
    return f"OBE Architects | New Consultation Lead #{short}"


def build_body_text(lead: dict) -> str:
    f = _lead_fields(lead)
    return (
        "----------------------------------------\n"
        "NEW LEAD RECEIVED\n"
        f"Lead ID: {f['id']}\n"
        f"Created: {f['created_at']}\n\n"
        "Customer\n"
        f"- Name: {f['name']}\n"
        f"- Email: {f['email']}\n"
        f"- Phone: {f['phone']}\n"
        f"- Consultant Type: {f['consultant_type']}\n"
        f"- Source: {f['source']}\n"
        f"- Session ID: {f['session_id']}\n"
        "----------------------------------------"
    )


def build_body_html(lead: dict) -> str:
    f = _lead_fields(lead)
    return f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f3f6fb;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
      New consultation lead from {escape(f['name'])}.
    </div>
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f3f6fb;padding:24px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="620" style="max-width:620px;width:100%;background:#ffffff;border:1px solid #d8e2f0;border-radius:12px;overflow:hidden;">
            <tr>
              <td style="padding:18px 24px;background:linear-gradient(135deg,#0f6fb5,#1a8ca3);color:#ffffff;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;">
                <div style="font-size:18px;font-weight:700;line-height:1.3;">New Consultation Lead</div>
                <div style="margin-top:6px;font-size:13px;opacity:0.92;">Lead ID: {escape(f['id'])}</div>
                <div style="margin-top:2px;font-size:12px;opacity:0.86;">Created: {escape(f['created_at'])}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 24px;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;color:#1d2a3b;">
                <div style="font-size:13px;font-weight:700;letter-spacing:0.4px;text-transform:uppercase;color:#57708f;margin-bottom:10px;">Customer Details</div>
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
                  <tr><td style="padding:8px 0;width:170px;font-size:13px;color:#5b6f88;">Name</td><td style="padding:8px 0;font-size:14px;font-weight:600;">{escape(f['name'])}</td></tr>
                  <tr><td style="padding:8px 0;width:170px;font-size:13px;color:#5b6f88;">Email</td><td style="padding:8px 0;font-size:14px;font-weight:600;">{escape(f['email'])}</td></tr>
                  <tr><td style="padding:8px 0;width:170px;font-size:13px;color:#5b6f88;">Phone</td><td style="padding:8px 0;font-size:14px;font-weight:600;">{escape(f['phone'])}</td></tr>
                  <tr><td style="padding:8px 0;width:170px;font-size:13px;color:#5b6f88;">Consultant Type</td><td style="padding:8px 0;font-size:14px;font-weight:600;">{escape(f['consultant_type'])}</td></tr>
                  <tr><td style="padding:8px 0;width:170px;font-size:13px;color:#5b6f88;">Source</td><td style="padding:8px 0;font-size:14px;font-weight:600;">{escape(f['source'])}</td></tr>
                  <tr><td style="padding:8px 0;width:170px;font-size:13px;color:#5b6f88;">Session ID</td><td style="padding:8px 0;font-size:14px;font-weight:600;">{escape(f['session_id'])}</td></tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:14px 24px;background:#f7f9fd;border-top:1px solid #d8e2f0;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;color:#67809b;font-size:12px;">
                OBE Architects Bot · Automated lead notification
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""".strip()
