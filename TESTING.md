# Testing

## Local WhatsApp Simulator

### Run Docker Compose

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

### Enable Mock WhatsApp Sends

Set the env var (local shell or `.env`):

```
WHATSAPP_MOCK_SEND=true
WHATSAPP_ACCESS_TOKEN=mock
WHATSAPP_PHONE_NUMBER_ID=mock
```

### Simulate Webhook Payloads (no Meta API)

Text message ("hi"):

```bash
curl -X POST http://127.0.0.1/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "id": "entry-1",
      "changes": [{
        "field": "messages",
        "value": {
          "messaging_product": "whatsapp",
          "metadata": {"display_phone_number": "15550001111", "phone_number_id": "123"},
          "contacts": [{"wa_id": "15551234567", "profile": {"name": "Test User"}}],
          "messages": [{
            "from": "15551234567",
            "id": "wamid-200",
            "timestamp": "1700000000",
            "type": "text",
            "text": {"body": "hi"}
          }]
        }
      }]
    }]
  }'
```

Talk to human (button reply):

```bash
curl -X POST http://127.0.0.1/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "id": "entry-1",
      "changes": [{
        "field": "messages",
        "value": {
          "messaging_product": "whatsapp",
          "metadata": {"display_phone_number": "15550001111", "phone_number_id": "123"},
          "contacts": [{"wa_id": "15551234567", "profile": {"name": "Test User"}}],
          "messages": [{
            "from": "15551234567",
            "id": "wamid-201",
            "timestamp": "1700000001",
            "type": "interactive",
            "interactive": {
              "type": "button_reply",
              "button_reply": {"id": "MENU_HUMAN", "title": "Talk to Human"}
            }
          }]
        }
      }]
    }]
  }'
```

### View Captured Mock Outbox

In tests, read with:

```
from app.services.whatsapp_mock import get_mock_outbox
```
