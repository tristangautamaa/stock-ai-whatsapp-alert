import pytest

from src.signals.engine import generate_signal
from src.signals.schemas import SignalType


def _bullish() -> dict:
    return {
        "close": 100.0, "ma20": 95.0, "ma50": 90.0, "ma200": 85.0,
        "rsi": 57.0, "volume_ratio": 1.5, "ma20_slope": 0.4,
        "macd_hist": 0.3, "atr": 2.0, "atr_pct": 2.0,
        "volatility_20d": 20.0, "above_ma20": True, "above_ma50": True,
        "above_ma200": True, "ma20_distance_pct": 5.3,
        "regime": "BULLISH", "volume_current": 1_500_000.0,
        "volume_ma20": 1_000_000.0, "volume_spike": False,
        "return_1d": 0.5, "return_5d": 2.1, "return_20d": 4.0,
        "bb_upper": 104.0, "bb_mid": 95.0, "bb_lower": 86.0, "bb_width": None,
        "ema9": 98.0,
    }


def _bearish() -> dict:
    return {
        "close": 85.0, "ma20": 90.0, "ma50": 93.0, "ma200": 97.0,
        "rsi": 37.0, "volume_ratio": 1.7, "ma20_slope": -0.6,
        "macd_hist": -0.4, "atr": 2.0, "atr_pct": 2.4,
        "volatility_20d": 25.0, "above_ma20": False, "above_ma50": False,
        "above_ma200": False, "ma20_distance_pct": -5.6,
        "regime": "BEARISH", "volume_current": 1_700_000.0,
        "volume_ma20": 1_000_000.0, "volume_spike": True,
        "return_1d": -1.2, "return_5d": -4.0, "return_20d": -8.0,
        "bb_upper": 96.0, "bb_mid": 90.0, "bb_lower": 84.0, "bb_width": None,
        "ema9": 87.0,
    }


def test_buy_signal_generated():
    sig = generate_signal("AAPL", _bullish())
    assert sig.signal_type == SignalType.BUY_WATCHLIST
    assert sig.confidence >= 60


def test_sell_signal_generated():
    sig = generate_signal("AAPL", _bearish())
    assert sig.signal_type == SignalType.SELL_WARNING
    assert sig.confidence >= 60


def test_avoid_on_missing_data():
    sig = generate_signal("AAPL", {"close": None, "ma20": None, "rsi": None, "atr": None})
    assert sig.signal_type == SignalType.AVOID


def test_avoid_on_low_volume():
    ind = _bullish()
    ind["volume_ratio"] = 0.2
    sig = generate_signal("AAPL", ind)
    assert sig.signal_type == SignalType.AVOID


def test_buy_signal_has_risk_control():
    sig = generate_signal("AAPL", _bullish())
    assert sig.risk_control is not None
    assert sig.risk_control.risk_reward >= 1.5


def test_buy_signal_has_reasons():
    sig = generate_signal("AAPL", _bullish())
    assert len(sig.reasons) > 0


def test_sell_has_invalidation():
    sig = generate_signal("AAPL", _bearish())
    assert len(sig.invalidation_conditions) > 0


def test_market_field_propagated():
    sig = generate_signal("BBCA.JK", _bullish(), market="IDX")
    assert sig.market == "IDX"
