import numpy as np
import pandas as pd
import pytest

from src.indicators.technicals import compute_indicators


def _make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    close = np.maximum(close, 1)
    return pd.DataFrame(
        {
            "open": close * (1 - rng.uniform(0, 0.005, n)),
            "high": close * (1 + rng.uniform(0, 0.015, n)),
            "low": close * (1 - rng.uniform(0, 0.015, n)),
            "close": close,
            "volume": rng.integers(500_000, 5_000_000, n).astype(float),
        },
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )


def test_returns_empty_for_empty_df():
    assert compute_indicators(pd.DataFrame()) == {}


def test_returns_empty_for_short_df():
    assert compute_indicators(_make_ohlcv(30)) == {}


def test_has_required_keys():
    ind = compute_indicators(_make_ohlcv(100))
    for key in ("ma20", "ma50", "rsi", "atr", "close", "volume_ratio", "regime"):
        assert key in ind, f"Missing key: {key}"


def test_rsi_in_range():
    ind = compute_indicators(_make_ohlcv(100))
    rsi = ind.get("rsi")
    assert rsi is not None
    assert 0 <= rsi <= 100


def test_ma_ordering_bullish():
    # Strongly trending up — MA20 should be above MA50 direction, both non-None
    n = 200
    close = np.linspace(50, 150, n)
    df = pd.DataFrame({
        "open": close * 0.998, "high": close * 1.01,
        "low": close * 0.99, "close": close,
        "volume": np.full(n, 1_000_000.0),
    }, index=pd.date_range("2020-01-01", periods=n, freq="D"))
    ind = compute_indicators(df)
    assert ind["ma20"] is not None
    assert ind["ma50"] is not None
    assert ind["above_ma20"] is True
    assert ind["regime"] == "BULLISH"


def test_volume_ratio_positive():
    ind = compute_indicators(_make_ohlcv(100))
    assert ind["volume_ratio"] is not None
    assert ind["volume_ratio"] > 0


def test_regime_values():
    ind = compute_indicators(_make_ohlcv(100))
    assert ind["regime"] in ("BULLISH", "BEARISH", "MIXED")
