# WhatsApp Cloud API Setup

## Option A — Meta WhatsApp Cloud API (Production)

### 1. Create a Meta App

1. Go to [developers.facebook.com](https://developers.facebook.com) → **My Apps** → **Create App**
2. Choose **Business** type
3. Add the **WhatsApp** product to your app

### 2. Get Credentials

In your App → WhatsApp → API Setup:

| .env Variable | Where to find it |
|---|---|
| `WHATSAPP_CLOUD_API_TOKEN` | Temporary token shown on the API Setup page (24h). For production, generate a System User token via Business Manager → System Users |
| `WHATSAPP_PHONE_NUMBER_ID` | Shown under **From** phone number on the API Setup page |
| `WHATSAPP_RECIPIENT_NUMBER` | The number to receive alerts. Format: international without `+` (e.g. `628123456789`) |
| `WHATSAPP_API_VERSION` | Use `v20.0` (default) |

### 3. Verify the Recipient

For sandbox/test numbers, you must **add the recipient number** as a verified test number in your app's WhatsApp settings before you can send to it.

### 4. Test a Send

```bash
# Set DRY_RUN=false in .env first, then:
python - <<'EOF'
from src.config import get_settings
from src.notifications.whatsapp_cloud import WhatsAppCloudNotifier
settings = get_settings()
n = WhatsAppCloudNotifier(settings)
n.send("Hello from Stock AI! Test message.")
EOF
```

### 5. Move to Production (Optional)

- Submit your app for Meta review to remove the test-number restriction
- Generate a permanent System User token from Business Manager

---

## Option B — Twilio WhatsApp Sandbox (Quick Dev)

1. Sign up at [twilio.com](https://twilio.com)
2. Go to **Messaging** → **Try WhatsApp**
3. Follow the sandbox join instructions (send a code from your WhatsApp)
4. Fill in your `.env`:

```
WHATSAPP_PROVIDER=twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_WHATSAPP_FROM=+14155238886   # Twilio sandbox number
TWILIO_WHATSAPP_TO=+628123456789    # Your personal number
```

Twilio sandbox is limited to numbers that have opted in, making it safe for solo dev testing.

---

## DRY_RUN Mode

When `DRY_RUN=true` (default), no message is sent. The formatted message is printed to stdout. Always test with dry-run before enabling live sends.
