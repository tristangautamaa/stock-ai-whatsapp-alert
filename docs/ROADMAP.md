# Roadmap

## MVP (v0.1) — Current
- [x] yfinance data provider
- [x] pandas-ta indicator engine (MA, RSI, MACD, BB, ATR, Volume)
- [x] Rule-based signal scoring (BUY_WATCHLIST, SELL_WARNING, HOLD, AVOID)
- [x] ATR-based risk controls (entry, stop, target, R/R)
- [x] Meta WhatsApp Cloud API sender
- [x] Twilio WhatsApp sandbox fallback
- [x] FastAPI TradingView webhook endpoint
- [x] Daily CLI watchlist scanner
- [x] Streamlit monitoring dashboard
- [x] vectorbt + pandas backtest
- [x] Optional LLM explanation (Claude / GPT-4o-mini)
- [x] Optional TimeGPT forecast
- [x] Optional FinBERT sentiment
- [x] Docker Compose deployment
- [x] GitHub Actions CI

## v0.2 — Near Term
- [ ] SQLite signal log (persist scan history across restarts)
- [ ] Sectors.app OHLCV integration for IDX
- [ ] Weekly email digest (HTML summary of week's signals)
- [ ] Slack notification adapter
- [ ] Additional signal types: BREAKOUT, REVERSAL_CANDIDATE

## v0.3 — Medium Term
- [ ] Multi-timeframe confluence (daily + weekly)
- [ ] PostgreSQL / TimescaleDB migration
- [ ] Advanced backtesting with position sizing
- [ ] Fundamental filter overlay (P/E, P/B from Sectors.app)
- [ ] Watchlist auto-update from IDX LQ45 index

## v1.0 — Production Hardening
- [ ] Redis caching for indicator results
- [ ] Rate limiting on webhook endpoint
- [ ] Prometheus metrics + Grafana dashboard
- [ ] Multi-user support with per-user watchlists
- [ ] Sector rotation heatmap
- [ ] IDX-specific corporate action adjustments

## Intentionally Out of Scope (forever)
- Auto trade execution (broker API integration)
- Real-time intraday scanning (not for daily timeframe MVP)
- Public-facing SaaS (private use only — check local regulations before commercializing)
