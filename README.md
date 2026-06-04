# stock-ai-whatsapp-alert

AI-assisted private stock alert system. Analyzes stocks daily, scores signals with rule-based logic + optional AI enrichment, and sends actionable WhatsApp notifications. **Does not execute trades.** All decisions are manual.

> ⚠️ **Disclaimer**: This system is for private research and decision support only. It does not guarantee profit. Market data may be delayed or incomplete. The user is solely responsible for every investment decision. Do not use as public paid investment advice without checking relevant financial regulations.

---

## Features

- **Signal engine**: BUY_WATCHLIST, SELL_WARNING, HOLD, AVOID with confidence score
- **Risk controls**: ATR-based entry zone, stop loss, target, risk/reward ratio
- **WhatsApp alerts**: Meta WhatsApp Cloud API (primary) + Twilio sandbox (fallback)
- **TradingView webhook**: POST `/webhook/tradingview` — receives Pine Script alerts
- **Daily scanner**: CLI tool scans a CSV watchlist and sends alerts above threshold
- **AI enrichment** (optional): Claude/GPT explanation, TimeGPT forecast, FinBERT sentiment
- **Streamlit dashboard**: visual monitoring, chart, indicators, backtest summary
- **Backtest**: vectorbt (or pandas fallback) with fees and slippage
- **IDX + US support**: yfinance covers both. Sectors.app adapter placeholder for IDX production data

---

## Quick Start

### 1. Install

```bash
cd stock-ai-whatsapp-alert
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — at minimum set DRY_RUN=true for safe testing
```

### 3. Run dry-run scan (US sample — no API keys needed)

```bash
python -m src.jobs.scan_watchlist --market US --watchlist watchlists/us_sample.csv
```

### 4. Run dry-run scan (IDX sample)

```bash
python -m src.jobs.scan_watchlist --market IDX --watchlist watchlists/idx_sample.csv
```

### 5. Start the dashboard

```bash
streamlit run app/dashboard.py
# → http://localhost:8501
```

### 6. Start the API server

```bash
uvicorn src.web.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

---

## Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `DRY_RUN` | `true` | Print alerts instead of sending |
| `MARKET_DATA_PROVIDER` | `yfinance` | Data source |
| `WHATSAPP_PROVIDER` | `meta` | `meta` or `twilio` |
| `SIGNAL_ALERT_THRESHOLD` | `65` | Min confidence to send alert |

---

## Test a Real WhatsApp Send

1. Set `DRY_RUN=false` in `.env`
2. Fill in WhatsApp credentials (see [docs/SETUP_WHATSAPP.md](docs/SETUP_WHATSAPP.md))
3. Run:

```bash
python - <<'EOF'
from src.config import get_settings
from src.notifications.whatsapp_cloud import WhatsAppCloudNotifier
n = WhatsAppCloudNotifier(get_settings())
n.send("Stock AI WhatsApp Alert — test message. System is working.")
EOF
```

---

## Simulate a TradingView Alert

```bash
curl -X POST http://localhost:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "action": "buy", "price": 180.5}'
```

---

## Run Tests

```bash
pytest tests/ -v
```

---

## Docker Compose

```bash
cp .env.example .env   # edit as needed
docker compose up --build
# API:       http://localhost:8000
# Dashboard: http://localhost:8501
```

---

## GitHub Setup

If GitHub CLI is installed:

```bash
gh auth login
bash scripts/setup_github.sh
```

Manual alternative:

```bash
git init && git checkout -b main
git add . && git commit -m "init: stock-ai-whatsapp-alert MVP"
gh repo create stock-ai-whatsapp-alert --private --source=. --remote=origin --push
```

---

## Project Structure

```
stock-ai-whatsapp-alert/
├── .github/workflows/ci.yml    # GitHub Actions lint + test
├── app/dashboard.py            # Streamlit dashboard
├── src/
│   ├── config.py               # Pydantic settings (.env)
│   ├── data/                   # Data providers (yfinance, Sectors.app)
│   ├── indicators/technicals.py# MA, RSI, MACD, BB, ATR, Volume
│   ├── signals/                # Scoring engine + risk controls + schemas
│   ├── ai/                     # LLM explanation, TimeGPT, FinBERT
│   ├── notifications/          # WhatsApp Cloud API, Twilio, formatter
│   ├── web/main.py             # FastAPI (health + TradingView webhook)
│   ├── backtesting/            # vectorbt / pandas backtest
│   └── jobs/scan_watchlist.py  # Daily CLI scanner
├── tests/                      # pytest test suite
├── watchlists/                 # idx_sample.csv, us_sample.csv
├── docs/                       # ARCHITECTURE, SETUP_WHATSAPP, SETUP_TRADINGVIEW, ROADMAP
├── scripts/                    # setup_github.sh, run_local.sh
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## What Needs API Keys

| Feature | Required Key | Optional? |
|---|---|---|
| Market data | None (yfinance is free) | ✅ Free |
| WhatsApp Meta | `WHATSAPP_CLOUD_API_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID` | Required for real sends |
| WhatsApp Twilio | `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` | Alternative to Meta |
| LLM explanation | `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` | ✅ Optional |
| TimeGPT forecast | `TIMEGPT_API_KEY` | ✅ Optional |
| FinBERT sentiment | None (local model) | ✅ Optional (heavy install) |
| IDX data (prod) | `SECTORS_API_KEY` | ✅ Optional (yfinance covers IDX) |

---

## What Is Not Yet Implemented

- SQLite/Postgres signal persistence (logs to stdout only in MVP)
- Sectors.app OHLCV endpoint (placeholder — waiting for confirmed API docs)
- Twelve Data / Finnhub / Alpaca adapters (TODO-ready files)
- Multi-timeframe confluence
- Fundamental data overlay
- Intraday scanning

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full plan.

---

## Branch Strategy

```
main        ← stable, tagged releases
develop     ← integration branch
feature/*   ← feature branches → PR to develop
hotfix/*    ← critical fixes → PR to main
```

---

## License

Private use only. Not for redistribution or commercial use without explicit permission.
