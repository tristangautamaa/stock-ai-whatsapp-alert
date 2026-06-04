# TradingView Webhook Setup

## How It Works

TradingView Pine Script strategy alerts can fire a webhook to this system's FastAPI server. The system then:

1. Receives the alert payload
2. Fetches fresh market data for the ticker
3. Computes indicators and scores the signal
4. Optionally overrides signal direction based on the TradingView action
5. Sends a formatted WhatsApp alert

## Step 1 — Expose Your Server

Your FastAPI server must be publicly reachable. Options:

| Method | Notes |
|---|---|
| **ngrok** (dev) | `ngrok http 8000` → copy the `https://xxxx.ngrok.io` URL |
| **Railway / Render** | Free tier works for low-volume alerts |
| **VPS / Docker** | Any cloud VM with port 8000 open |
| **Cloudflare Tunnel** | Free, stable alternative to ngrok |

## Step 2 — Configure TradingView Alert

In TradingView → right-click a strategy or indicator → **Add Alert**:

- **Condition**: your signal condition
- **Webhook URL**: `https://your-server.com/webhook/tradingview`
- **Message** (JSON format recommended):

```json
{
  "ticker": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "strategy": "{{strategy.order.id}}"
}
```

## Step 3 — Optional Secret

To protect the webhook from unauthorized calls, set a shared secret:

```
# .env
TRADINGVIEW_WEBHOOK_SECRET=your-random-secret-here
```

Then in TradingView alert, add an HTTP header:
```
X-Webhook-Secret: your-random-secret-here
```

## Testing Locally

```bash
# Start the server
uvicorn src.web.main:app --reload

# Simulate a TradingView webhook
curl -X POST http://localhost:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "action": "buy", "price": 180.5}'
```

## Supported Action Values

| TradingView `action` | System Behavior |
|---|---|
| `buy` / `long` | Forces `BUY_WATCHLIST` signal type |
| `sell` / `short` / `close` | Forces `SELL_WARNING` signal type |
| anything else | System computes signal from indicators |
