import pandas as pd
import numpy as np
from typing import Optional
from loguru import logger

from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator, EMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

MIN_ROWS = 50


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add TA columns to a copy of the OHLCV DataFrame.
    Requires lowercase columns: open, high, low, close, volume.
    """
    if df.empty or len(df) < MIN_ROWS:
        return df

    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Moving Averages
    df["ma20"] = SMAIndicator(close, window=20).sma_indicator()
    df["ma50"] = SMAIndicator(close, window=50).sma_indicator()
    df["ma200"] = SMAIndicator(close, window=200).sma_indicator()
    df["ema9"] = EMAIndicator(close, window=9).ema_indicator()
    df["ma20_slope"] = df["ma20"].diff(5)

    # RSI
    df["rsi"] = RSIIndicator(close, window=14).rsi()

    # MACD
    _macd = MACD(close, window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = _macd.macd()
    df["macd_signal"] = _macd.macd_signal()
    df["macd_diff"] = _macd.macd_diff()

    # Bollinger Bands
    _bb = BollingerBands(close, window=20, window_dev=2)
    df["bb_upper"] = _bb.bollinger_hband()
    df["bb_middle"] = _bb.bollinger_mavg()
    df["bb_lower"] = _bb.bollinger_lband()
    df["bb_width"] = _bb.bollinger_wband()

    # ATR
    df["atr"] = AverageTrueRange(high, low, close, window=14).average_true_range()

    # Volume
    df["volume_ma20"] = volume.rolling(20).mean()
    df["volume_ratio"] = volume / df["volume_ma20"]

    # Returns and volatility
    df["return_1d"] = close.pct_change() * 100
    df["volatility_20"] = close.pct_change().rolling(20).std() * np.sqrt(252) * 100

    # Uppercase aliases for backward compatibility
    df["MA20"] = df["ma20"]
    df["MA50"] = df["ma50"]
    df["MA200"] = df["ma200"]
    df["RSI"] = df["rsi"]
    df["MACD"] = df["macd"]
    df["MACD_SIGNAL"] = df["macd_signal"]
    df["ATR"] = df["atr"]

    return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible alias for add_technical_indicators."""
    return add_technical_indicators(df)


def compute_indicators(df: pd.DataFrame) -> dict:
    """
    Compute technical indicators for a standardized OHLCV DataFrame.
    Returns a flat dict of scalar values for the latest bar.
    Returns {} if data is insufficient.
    """
    if df.empty or len(df) < MIN_ROWS:
        return {}

    enriched = add_technical_indicators(df)
    if enriched.empty:
        return {}

    last = enriched.iloc[-1]
    close = df["close"]
    volume = df["volume"]
    cur_close = float(close.iloc[-1])

    result: dict = {}

    # Moving averages
    result["ma20"] = _v(last, "ma20")
    result["ma50"] = _v(last, "ma50")
    result["ma200"] = _v(last, "ma200")
    result["ema9"] = _v(last, "ema9")
    result["ma20_slope"] = _v(last, "ma20_slope")

    # RSI
    result["rsi"] = _v(last, "rsi")

    # MACD (signal engine uses macd_line / macd_hist / macd_signal)
    result["macd_line"] = _v(last, "macd")
    result["macd_signal"] = _v(last, "macd_signal")
    result["macd_hist"] = _v(last, "macd_diff")

    # Bollinger Bands
    result["bb_upper"] = _v(last, "bb_upper")
    result["bb_mid"] = _v(last, "bb_middle")
    result["bb_lower"] = _v(last, "bb_lower")
    result["bb_width"] = _v(last, "bb_width")

    # ATR
    result["atr"] = _v(last, "atr")
    result["atr_pct"] = (result["atr"] / cur_close * 100) if result["atr"] else None

    # Volume
    result["volume_ma20"] = _v(last, "volume_ma20")
    result["volume_current"] = float(volume.iloc[-1])
    result["volume_ratio"] = _v(last, "volume_ratio")
    result["volume_spike"] = bool(result.get("volume_ratio") and result["volume_ratio"] > 1.5)

    # Price vs MAs
    result["close"] = cur_close
    result["above_ma20"] = bool(result["ma20"] and cur_close > result["ma20"])
    result["above_ma50"] = bool(result["ma50"] and cur_close > result["ma50"])
    result["above_ma200"] = bool(result["ma200"] and cur_close > result["ma200"])
    result["ma20_distance_pct"] = (
        (cur_close - result["ma20"]) / result["ma20"] * 100
        if result["ma20"] else None
    )

    # Returns and volatility
    result["volatility_20d"] = _v(last, "volatility_20")
    result["return_1d"] = _v(last, "return_1d")
    result["return_5d"] = float((close.iloc[-1] / close.iloc[-6] - 1) * 100) if len(close) > 6 else None
    result["return_20d"] = float((close.iloc[-1] / close.iloc[-21] - 1) * 100) if len(close) > 21 else None

    # Market regime
    result["regime"] = _regime(result)

    return result


def _v(row: pd.Series, col: str) -> Optional[float]:
    if col not in row.index:
        return None
    val = row[col]
    return None if pd.isna(val) else float(val)


def _regime(ind: dict) -> str:
    if ind.get("above_ma200") and ind.get("above_ma50") and ind.get("above_ma20"):
        return "BULLISH"
    if not ind.get("above_ma50") and not ind.get("above_ma20"):
        return "BEARISH"
    return "MIXED"
