"""
Backtest the rule-based signal strategy.

Uses vectorbt when available; falls back to a simple pandas implementation.

Usage:
    from src.backtesting.backtest_rules import run_backtest
    metrics = run_backtest("AAPL", period="2y")
"""
import numpy as np
import pandas as pd
from typing import Optional
from loguru import logger

from ..config import get_settings
from ..data.provider_factory import get_provider
from ..indicators.technicals import compute_indicators, MIN_ROWS


def _build_signal_series(df: pd.DataFrame) -> pd.Series:
    """Row-by-row signal generation over the historical DataFrame."""
    signals = pd.Series(0, index=df.index, dtype=int)
    for i in range(MIN_ROWS, len(df)):
        ind = compute_indicators(df.iloc[: i + 1])
        if not ind:
            continue
        above_ma20 = ind.get("above_ma20", False)
        above_ma50 = ind.get("above_ma50", False)
        rsi = ind.get("rsi") or 0
        vol_ratio = ind.get("volume_ratio") or 0

        if above_ma20 and above_ma50 and 45 <= rsi <= 70 and vol_ratio >= 1.2:
            signals.iloc[i] = 1
        elif not above_ma20 and rsi < 45:
            signals.iloc[i] = -1
    return signals


def run_backtest(
    ticker: str,
    period: str = "2y",
    fees: float = 0.001,
    slippage: float = 0.001,
) -> Optional[dict]:
    """
    Backtest the rule-based strategy on historical data.

    Args:
        ticker:   Ticker symbol (e.g. "AAPL" or "BBCA.JK")
        period:   yfinance period string ("1y", "2y", "3y")
        fees:     Round-trip fee per trade (0.001 = 0.1%)
        slippage: One-way slippage estimate

    Returns:
        Dict of performance metrics, or None on failure.
    """
    settings = get_settings()
    provider = get_provider(settings)

    df = provider.get_ohlcv(ticker, period=period)
    if df.empty:
        logger.error(f"Backtest aborted — no data for {ticker}")
        return None

    logger.info(f"Building signal series for {ticker} ({len(df)} bars)...")
    signals = _build_signal_series(df)

    try:
        import vectorbt as vbt
        return _run_vectorbt(df, signals, ticker, period, fees, slippage)
    except ImportError:
        logger.info("vectorbt not installed — using pandas backtest fallback")
        return _run_pandas(df, signals, ticker, period, fees, slippage)


def _run_vectorbt(
    df: pd.DataFrame,
    signals: pd.Series,
    ticker: str,
    period: str,
    fees: float,
    slippage: float,
) -> dict:
    import vectorbt as vbt

    close = df["close"]
    entries = signals == 1
    exits = signals == -1

    pf = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        fees=fees,
        slippage=slippage,
        freq="D",
    )
    stats = pf.stats()
    return {
        "ticker": ticker,
        "period": period,
        "engine": "vectorbt",
        "total_return_pct": round(float(stats.get("Total Return [%]", 0)), 2),
        "win_rate_pct": round(float(stats.get("Win Rate [%]", 0)), 2),
        "max_drawdown_pct": round(float(stats.get("Max Drawdown [%]", 0)), 2),
        "sharpe_ratio": round(float(stats.get("Sharpe Ratio", 0)), 3),
        "num_trades": int(stats.get("Total Trades", 0)),
        "fees_paid": round(float(stats.get("Total Fees Paid", 0)), 4),
    }


def _run_pandas(
    df: pd.DataFrame,
    signals: pd.Series,
    ticker: str,
    period: str,
    fees: float,
    slippage: float,
) -> dict:
    close = df["close"]
    position = 0
    entry_price = 0.0
    trades: list[float] = []

    for i in range(len(signals)):
        sig = int(signals.iloc[i])
        price = float(close.iloc[i])

        if sig == 1 and position == 0:
            entry_price = price * (1 + slippage)
            position = 1
        elif sig == -1 and position == 1:
            exit_price = price * (1 - slippage)
            pnl = (exit_price - entry_price) / entry_price - 2 * fees
            trades.append(pnl)
            position = 0

    if not trades:
        return {"ticker": ticker, "period": period, "engine": "pandas", "num_trades": 0,
                "total_return_pct": 0, "win_rate_pct": 0, "max_drawdown_pct": 0,
                "sharpe_ratio": 0, "fees_paid": 0}

    equity = pd.Series([1.0] + [1 + t for t in trades]).cumprod()
    total_return = (equity.iloc[-1] - 1) * 100
    win_rate = sum(1 for t in trades if t > 0) / len(trades) * 100
    rets = pd.Series(trades)
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    max_dd = float(((equity / equity.cummax()) - 1).min() * 100)

    return {
        "ticker": ticker,
        "period": period,
        "engine": "pandas",
        "total_return_pct": round(total_return, 2),
        "win_rate_pct": round(win_rate, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 3),
        "num_trades": len(trades),
        "fees_paid": round(len(trades) * fees * 2, 4),
    }
