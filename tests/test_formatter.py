import pytest
from datetime import datetime

from src.notifications.formatter import format_whatsapp_message
from src.signals.schemas import RiskControl, Signal, SignalType


def _signal(signal_type: SignalType = SignalType.BUY_WATCHLIST) -> Signal:
    return Signal(
        ticker="BBCA.JK",
        signal_type=signal_type,
        confidence=72,
        reasons=[
            "Price is above MA20 (short-term uptrend)",
            "Volume is 1.5× the 20-day average",
            "RSI 58.0 — bullish range, not overbought",
        ],
        invalidation_conditions=[
            "Daily close falls below MA20 (9,400)",
            "High-volume bearish candle confirming breakdown",
        ],
        risk_control=RiskControl(
            entry_low=9_600.0,
            entry_high=9_750.0,
            stop_loss=9_250.0,
            target=10_300.0,
            risk_reward=2.1,
            atr=150.0,
        ),
        market="IDX",
        timestamp=datetime(2024, 6, 1),
    )


def test_contains_ticker():
    assert "BBCA.JK" in format_whatsapp_message(_signal())


def test_contains_signal_type():
    msg = format_whatsapp_message(_signal())
    assert "BUY_WATCHLIST" in msg


def test_contains_risk_controls():
    msg = format_whatsapp_message(_signal())
    assert "Stop Loss" in msg
    assert "Target" in msg
    assert "Risk/Reward" in msg


def test_contains_disclaimer():
    msg = format_whatsapp_message(_signal())
    assert "Not financial advice" in msg or "AI-assisted" in msg


def test_sell_warning_format():
    msg = format_whatsapp_message(_signal(SignalType.SELL_WARNING))
    assert "SELL_WARNING" in msg


def test_avoid_format_no_crash():
    sig = Signal(
        ticker="JUNK",
        signal_type=SignalType.AVOID,
        confidence=0,
        reasons=["Insufficient data"],
        market="IDX",
    )
    msg = format_whatsapp_message(sig)
    assert "JUNK" in msg
    assert "AVOID" in msg


def test_ai_explanation_included():
    sig = _signal()
    sig.ai_explanation = "The stock shows strong momentum signals."
    msg = format_whatsapp_message(sig)
    assert "strong momentum" in msg


def test_timegpt_forecast_included():
    sig = _signal()
    sig.timegpt_forecast = {
        "horizon_days": 5,
        "direction": "UP",
        "expected_change_pct": 3.2,
        "avg_forecast": 10050.0,
        "forecasted_values": [],
    }
    msg = format_whatsapp_message(sig)
    assert "TimeGPT" in msg
    assert "UP" in msg
