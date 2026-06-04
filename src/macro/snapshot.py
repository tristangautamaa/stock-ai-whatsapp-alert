"""
Macro market snapshot via yfinance.

Covers world equity indices, volatility, commodities, rates, the dollar,
and Indonesian market / FX data.

NOTE: Hard macro statistics (BI 7-day reverse repo rate, CPI, GDP growth,
current account) and live macro news are NOT sourced here. Those come from
the Claude report step, which performs live web research at run time.
"""

from __future__ import annotations

from typing import Optional

import yfinance as yf
from loguru import logger


# ── Ticker registry ───────────────────────────────────────────────────────────

_WORLD_TICKERS: dict[str, str] = {
    "sp500":        "^GSPC",
    "nasdaq":       "^IXIC",
    "dow":          "^DJI",
    "vix":          "^VIX",
    "oil_wti":      "CL=F",
    "gold":         "GC=F",
    "us_10y_yield": "^TNX",
    "dxy":          "DX-Y.NYB",
}

_INDONESIA_TICKERS: dict[str, str] = {
    "idx_composite": "^JKSE",
    "usd_idr":       "IDR=X",
}

_ALL_TICKERS: dict[str, str] = {**_WORLD_TICKERS, **_INDONESIA_TICKERS}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_quotes(tickers: list[str]) -> dict[str, tuple[float, float]]:
    """
    Batch-fetch the last two closing prices for each ticker.
    Returns {ticker: (last_price, prev_close)}.
    Tickers that fail or have insufficient history are omitted.
    """
    if not tickers:
        return {}

    results: dict[str, tuple[float, float]] = {}
    try:
        raw = yf.download(
            tickers,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if raw.empty:
            return results

        close = raw.get("Close", raw.get("close"))
        if close is None:
            return results

        # Single-ticker download → Series; multi → DataFrame
        if hasattr(close, "columns"):
            for t in tickers:
                if t not in close.columns:
                    logger.warning(f"[macro] No data for {t}")
                    continue
                series = close[t].dropna()
                if len(series) >= 2:
                    results[t] = (float(series.iloc[-1]), float(series.iloc[-2]))
                elif len(series) == 1:
                    results[t] = (float(series.iloc[-1]), float(series.iloc[-1]))
        else:
            series = close.dropna()
            if tickers and len(series) >= 2:
                results[tickers[0]] = (float(series.iloc[-1]), float(series.iloc[-2]))
            elif tickers and len(series) == 1:
                results[tickers[0]] = (float(series.iloc[-1]), float(series.iloc[-1]))

    except Exception as exc:
        logger.error(f"[macro] Batch fetch failed: {exc}")

    return results


def _pct_change(last: float, prev: float) -> Optional[float]:
    if prev == 0:
        return None
    return round((last - prev) / prev * 100, 2)


def _entry(
    quotes: dict[str, tuple[float, float]],
    ticker: str,
    decimals: int = 2,
) -> dict[str, Optional[float]]:
    """Return {last, change_pct} for one ticker; both None on miss."""
    pair = quotes.get(ticker)
    if pair is None:
        return {"last": None, "change_pct": None}
    last, prev = pair
    return {
        "last": round(last, decimals),
        "change_pct": _pct_change(last, prev),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def get_macro_snapshot() -> dict:
    """
    Return a single-level dict with last price and daily % change for:

    World
      sp500, nasdaq, dow, vix, oil_wti, gold, us_10y_yield, dxy

    Indonesia
      idx_composite, usd_idr

    Each key maps to {"last": float | None, "change_pct": float | None}.
    Any ticker that yfinance cannot resolve returns both values as None.
    """
    all_symbols = list(_ALL_TICKERS.values())
    quotes = _fetch_quotes(all_symbols)

    snapshot: dict = {}

    # World markets
    snapshot["sp500"]        = _entry(quotes, "^GSPC")
    snapshot["nasdaq"]       = _entry(quotes, "^IXIC")
    snapshot["dow"]          = _entry(quotes, "^DJI")
    snapshot["vix"]          = _entry(quotes, "^VIX")
    snapshot["oil_wti"]      = _entry(quotes, "CL=F")
    snapshot["gold"]         = _entry(quotes, "GC=F",    decimals=0)
    snapshot["us_10y_yield"] = _entry(quotes, "^TNX",    decimals=3)
    snapshot["dxy"]          = _entry(quotes, "DX-Y.NYB")

    # Indonesia
    snapshot["idx_composite"] = _entry(quotes, "^JKSE",  decimals=0)
    snapshot["usd_idr"]       = _entry(quotes, "IDR=X",  decimals=0)

    return snapshot


def get_macro_summary_text(snapshot: dict | None = None) -> str:
    """
    Render the macro snapshot as a compact human-readable block.
    Fetches a fresh snapshot when none is supplied.

    Example output:
        === Macro Snapshot ===
        [World]
        S&P 500       5,304.72   +0.51%
        Nasdaq        16,780.00   -0.12%
        ...
        [Indonesia]
        IDX Composite  7,112     +0.38%
        USD/IDR       16,245     -0.07%
    """
    if snapshot is None:
        snapshot = get_macro_snapshot()

    def _fmt_last(val: Optional[float], decimals: int = 2) -> str:
        if val is None:
            return "  N/A"
        if val >= 1_000:
            return f"{val:>10,.{decimals}f}"
        return f"{val:>10.{decimals}f}"

    def _fmt_chg(val: Optional[float]) -> str:
        if val is None:
            return "     N/A"
        sign = "+" if val >= 0 else ""
        return f"  {sign}{val:.2f}%"

    rows: list[tuple[str, str, int]] = [
        # (label, key, decimals)
        ("[World]",          "",            0),
        ("S&P 500",          "sp500",       2),
        ("Nasdaq",           "nasdaq",      2),
        ("Dow Jones",        "dow",         2),
        ("VIX",              "vix",         2),
        ("Oil WTI ($/bbl)",  "oil_wti",     2),
        ("Gold ($/oz)",      "gold",        0),
        ("US 10Y Yield",     "us_10y_yield", 3),
        ("DXY",              "dxy",         2),
        ("",                 "",            0),
        ("[Indonesia]",      "",            0),
        ("IDX Composite",    "idx_composite", 0),
        ("USD/IDR",          "usd_idr",     0),
    ]

    lines = ["=== Macro Snapshot ==="]
    for label, key, decimals in rows:
        if key == "":
            lines.append(label)
            continue
        entry = snapshot.get(key, {"last": None, "change_pct": None})
        last_str = _fmt_last(entry.get("last"), decimals)
        chg_str  = _fmt_chg(entry.get("change_pct"))
        lines.append(f"  {label:<22}{last_str}{chg_str}")

    return "\n".join(lines)
