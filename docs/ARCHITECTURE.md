# Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                  stock-ai-whatsapp-alert                        │
│                                                                 │
│  TradingView Alert ──→ FastAPI /webhook/tradingview             │
│                                    │                            │
│  Daily Cron/CLI ───→ scan_watchlist.py                         │
│                                    │                            │
│                        ┌───────────▼────────────┐              │
│                        │    Data Provider       │              │
│                        │  yfinance / Sectors    │              │
│                        └───────────┬────────────┘              │
│                                    │ OHLCV DataFrame            │
│                        ┌───────────▼────────────┐              │
│                        │  Indicator Engine      │              │
│                        │  (pandas-ta)           │              │
│                        └───────────┬────────────┘              │
│                                    │ indicators dict            │
│                        ┌───────────▼────────────┐              │
│                        │   Signal Engine        │              │
│                        │  Rule-based scoring    │              │
│                        │  + Risk Controls (ATR) │              │
│                        └───────────┬────────────┘              │
│                                    │ Signal object              │
│                        ┌───────────▼────────────┐              │
│                        │   AI Enrichment        │              │
│                        │  TimeGPT (optional)    │              │
│                        │  FinBERT (optional)    │              │
│                        │  LLM explanation       │              │
│                        └───────────┬────────────┘              │
│                                    │                            │
│                        ┌───────────▼────────────┐              │
│                        │   Alert Formatter      │              │
│                        └───────────┬────────────┘              │
│                                    │ WhatsApp message text      │
│                        ┌───────────▼────────────┐              │
│                        │  WhatsApp Notifier     │              │
│                        │  Meta Cloud API        │              │
│                        │  Twilio (fallback)     │              │
│                        └────────────────────────┘              │
│                                                                 │
│  Streamlit Dashboard ──────────────────────── monitoring only  │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

1. **No auto-trading** — system only sends alerts. All execution is manual.
2. **Integration-first** — uses pandas-ta, yfinance, vectorbt, FastAPI, Streamlit. No raw reimplementation.
3. **Graceful degradation** — AI/TimeGPT/sentiment layers are all optional. Missing API keys skip the layer silently.
4. **Grounded AI** — LLM explanations are always prompted with computed indicator data. No fabrication.
5. **Dry-run by default** — `DRY_RUN=true` in `.env.example` ensures no accidental sends.

## Module Map

| Module | Purpose |
|---|---|
| `src/config.py` | Pydantic Settings — reads .env |
| `src/data/` | Abstract provider + yfinance impl |
| `src/indicators/technicals.py` | MA, RSI, MACD, BB, ATR, Volume |
| `src/signals/engine.py` | Rule scoring → Signal |
| `src/signals/risk.py` | ATR-based entry/stop/target |
| `src/signals/schemas.py` | Pydantic models |
| `src/ai/explanation.py` | LLM explanation (Claude/GPT) |
| `src/ai/timegpt_client.py` | Nixtla TimeGPT forecast |
| `src/ai/sentiment.py` | FinBERT news sentiment |
| `src/notifications/` | Formatter + Meta Cloud API + Twilio |
| `src/web/main.py` | FastAPI server + TradingView webhook |
| `src/jobs/scan_watchlist.py` | CLI daily scanner |
| `src/backtesting/backtest_rules.py` | vectorbt / pandas backtest |
| `app/dashboard.py` | Streamlit visual dashboard |

## Storage (MVP)

No persistent store in MVP. Logs go to stdout via loguru.
Migration path: add SQLite → PostgreSQL/TimescaleDB as `src/db/` module.
