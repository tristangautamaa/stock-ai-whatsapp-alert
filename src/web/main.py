from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from loguru import logger

from ..config import get_settings
from ..data.provider_factory import get_provider
from ..indicators.technicals import compute_indicators
from ..signals.engine import generate_signal
from ..signals.schemas import SignalType
from ..notifications.formatter import format_whatsapp_message
from ..notifications import get_notifier

app = FastAPI(
    title="Stock AI WhatsApp Alert",
    description="AI-assisted stock alert system — private decision support only. Does not execute trades.",
    version="0.1.0",
)


@app.get("/health")
async def health():
    s = get_settings()
    return {
        "status": "ok",
        "env": s.app_env,
        "dry_run": s.dry_run,
        "data_provider": s.market_data_provider,
        "whatsapp_provider": s.whatsapp_provider,
    }


@app.post("/webhook/tradingview")
async def tradingview_webhook(
    request: Request,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
):
    """
    Receives alerts from TradingView Pine Script strategy alerts.
    Set the TradingView alert message to JSON, e.g.:
      {"ticker": "{{ticker}}", "action": "{{strategy.order.action}}", "price": {{close}}}
    """
    settings = get_settings()

    if settings.tradingview_webhook_secret:
        if x_webhook_secret != settings.tradingview_webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # TradingView sends either JSON or plain text
    try:
        body = await request.json()
    except Exception:
        raw = await request.body()
        body = {"message": raw.decode("utf-8", errors="replace"), "ticker": "UNKNOWN"}

    logger.info(f"TradingView webhook: {body}")

    ticker = str(body.get("ticker", body.get("symbol", "UNKNOWN"))).upper().strip()
    action = str(body.get("action", "neutral")).lower()

    provider = get_provider(settings)
    df = provider.get_ohlcv(ticker)
    if df.empty:
        return JSONResponse(
            {"status": "error", "detail": f"No market data for {ticker}"},
            status_code=422,
        )

    indicators = compute_indicators(df)
    signal = generate_signal(ticker, indicators)

    # Override signal direction if TradingView sent an explicit action
    if action in ("buy", "long"):
        signal.signal_type = SignalType.BUY_WATCHLIST
    elif action in ("sell", "short", "close"):
        signal.signal_type = SignalType.SELL_WARNING

    message = format_whatsapp_message(signal)
    notifier = get_notifier(settings)
    sent = notifier.send(message)

    return {
        "status": "ok",
        "ticker": ticker,
        "signal": signal.signal_type.value,
        "confidence": signal.confidence,
        "sent": sent,
    }


@app.post("/scan/{ticker}")
async def scan_ticker(ticker: str):
    """Quick one-off scan for a single ticker."""
    settings = get_settings()
    provider = get_provider(settings)
    df = provider.get_ohlcv(ticker.upper())
    if df.empty:
        return JSONResponse({"status": "error", "detail": "No data"}, status_code=422)

    indicators = compute_indicators(df)
    signal = generate_signal(ticker.upper(), indicators)

    return {
        "ticker": signal.ticker,
        "signal": signal.signal_type.value,
        "confidence": signal.confidence,
        "reasons": signal.reasons,
        "risk_control": signal.risk_control.model_dump() if signal.risk_control else None,
    }
