"""
Portfolio valuation module.

load_holdings()  — reads a CSV of positions
value_portfolio() — fetches live prices and returns per-position + totals
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yfinance as yf
from loguru import logger


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Position:
    ticker: str
    shares: float
    avg_cost: float        # native currency per share
    market: str            # "IDX" or "US"
    last_price: Optional[float] = None
    prev_close: Optional[float] = None

    @property
    def cost_basis(self) -> float:
        return self.shares * self.avg_cost

    @property
    def market_value(self) -> Optional[float]:
        if self.last_price is None:
            return None
        return self.shares * self.last_price

    @property
    def unrealized_pl(self) -> Optional[float]:
        mv = self.market_value
        return None if mv is None else mv - self.cost_basis

    @property
    def unrealized_pl_pct(self) -> Optional[float]:
        if self.unrealized_pl is None or self.cost_basis == 0:
            return None
        return self.unrealized_pl / self.cost_basis * 100

    @property
    def day_change(self) -> Optional[float]:
        if self.last_price is None or self.prev_close is None:
            return None
        return (self.last_price - self.prev_close) * self.shares

    @property
    def day_change_pct(self) -> Optional[float]:
        if self.last_price is None or self.prev_close is None or self.prev_close == 0:
            return None
        return (self.last_price - self.prev_close) / self.prev_close * 100


@dataclass
class PortfolioSummary:
    positions: list[PositionResult]
    total_cost_basis: float
    total_market_value: float
    total_unrealized_pl: float
    total_unrealized_pl_pct: float
    total_day_change: Optional[float]
    # USD/IDR rate for US→IDR conversion
    usd_idr_rate: Optional[float] = None
    # Total portfolio value expressed in IDR (IDX native + US converted)
    total_value_idr: Optional[float] = None


@dataclass
class PositionResult:
    ticker: str
    market: str
    shares: float
    avg_cost: float
    last_price: Optional[float]
    market_value: Optional[float]
    unrealized_pl: Optional[float]
    unrealized_pl_pct: Optional[float]
    day_change: Optional[float]
    day_change_pct: Optional[float]
    weight_pct: Optional[float]        # % of total portfolio market value
    # For US positions: equivalent IDR value using live USD/IDR
    market_value_idr: Optional[float] = None


# ── CSV loader ────────────────────────────────────────────────────────────────

def load_holdings(path: str | Path = "portfolio/holdings.csv") -> list[Position]:
    """
    Read holdings from a CSV file.

    Required columns: ticker, shares, avg_cost, market
    Skips blank lines and lines starting with '#'.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Holdings file not found: {path}")

    holdings: list[Position] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Re-feed non-comment lines into DictReader
            break
        fh.seek(0)

        filtered = (
            line for line in fh
            if line.strip() and not line.strip().startswith("#")
        )
        reader = csv.DictReader(filtered)
        for row in reader:
            try:
                holdings.append(Position(
                    ticker=row["ticker"].strip().upper(),
                    shares=float(row["shares"]),
                    avg_cost=float(row["avg_cost"]),
                    market=row["market"].strip().upper(),
                ))
            except (KeyError, ValueError) as exc:
                logger.warning(f"Skipping bad row {row}: {exc}")

    logger.info(f"Loaded {len(holdings)} holdings from {path}")
    return holdings


# ── Price fetching ────────────────────────────────────────────────────────────

def _fetch_last_prices(tickers: list[str]) -> dict[str, tuple[float, float]]:
    """
    Fetch (last_price, prev_close) for each ticker using yfinance.
    Returns a dict {ticker: (last_price, prev_close)}.
    Missing/failed tickers are omitted.
    """
    if not tickers:
        return {}

    results: dict[str, tuple[float, float]] = {}
    try:
        data = yf.download(
            tickers,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if data.empty:
            return results

        close = data["Close"] if "Close" in data.columns else data.get("close")
        if close is None:
            return results

        # Single-ticker download returns a Series, multi returns DataFrame
        if hasattr(close, "columns"):
            for t in tickers:
                col = t
                if col not in close.columns:
                    logger.warning(f"[portfolio] No close data for {t}")
                    continue
                series = close[col].dropna()
                if len(series) >= 2:
                    results[t] = (float(series.iloc[-1]), float(series.iloc[-2]))
                elif len(series) == 1:
                    results[t] = (float(series.iloc[-1]), float(series.iloc[-1]))
        else:
            # Single ticker — close is a Series
            series = close.dropna()
            if tickers and len(series) >= 2:
                results[tickers[0]] = (float(series.iloc[-1]), float(series.iloc[-2]))
            elif tickers and len(series) == 1:
                results[tickers[0]] = (float(series.iloc[-1]), float(series.iloc[-1]))

    except Exception as exc:
        logger.error(f"[portfolio] Batch price fetch failed: {exc}")

    return results


def _fetch_usd_idr() -> Optional[float]:
    """Fetch the current USD/IDR exchange rate via yfinance (ticker: USDIDR=X)."""
    try:
        data = yf.download("USDIDR=X", period="5d", interval="1d", progress=False, auto_adjust=True)
        if data.empty:
            return None
        close = data["Close"].dropna() if "Close" in data.columns else None
        if close is None or close.empty:
            return None
        rate = float(close.iloc[-1])
        logger.info(f"[portfolio] USD/IDR rate: {rate:,.0f}")
        return rate
    except Exception as exc:
        logger.error(f"[portfolio] USD/IDR fetch failed: {exc}")
        return None


# ── Main valuation function ───────────────────────────────────────────────────

def value_portfolio(
    holdings: list[Position],
    usd_idr_rate: Optional[float] = None,
) -> PortfolioSummary:
    """
    Fetch live prices for all holdings and compute per-position and portfolio totals.

    Args:
        holdings:     List of Position objects (from load_holdings).
        usd_idr_rate: Override USD/IDR rate. If None and US positions exist,
                      fetched automatically from yfinance.

    Returns:
        PortfolioSummary with per-position PositionResult list and aggregate totals.
    """
    if not holdings:
        return PortfolioSummary(
            positions=[],
            total_cost_basis=0.0,
            total_market_value=0.0,
            total_unrealized_pl=0.0,
            total_unrealized_pl_pct=0.0,
            total_day_change=None,
        )

    tickers = [h.ticker for h in holdings]
    prices = _fetch_last_prices(tickers)

    # Populate last_price / prev_close on each Position
    for pos in holdings:
        pair = prices.get(pos.ticker)
        if pair:
            pos.last_price, pos.prev_close = pair
        else:
            logger.warning(f"[portfolio] Could not fetch price for {pos.ticker}")

    # Fetch USD/IDR only if needed
    has_us = any(h.market == "US" for h in holdings)
    if has_us and usd_idr_rate is None:
        usd_idr_rate = _fetch_usd_idr()

    # Compute total market value for weight calculation (skip positions with no price)
    total_mv = sum(
        h.market_value for h in holdings if h.market_value is not None
    )

    results: list[PositionResult] = []
    for pos in holdings:
        mv = pos.market_value
        weight = (mv / total_mv * 100) if (mv is not None and total_mv > 0) else None

        mv_idr: Optional[float] = None
        if pos.market == "US" and mv is not None and usd_idr_rate is not None:
            mv_idr = mv * usd_idr_rate

        results.append(PositionResult(
            ticker=pos.ticker,
            market=pos.market,
            shares=pos.shares,
            avg_cost=pos.avg_cost,
            last_price=pos.last_price,
            market_value=mv,
            unrealized_pl=pos.unrealized_pl,
            unrealized_pl_pct=pos.unrealized_pl_pct,
            day_change=pos.day_change,
            day_change_pct=pos.day_change_pct,
            weight_pct=weight,
            market_value_idr=mv_idr,
        ))

    total_cost = sum(h.cost_basis for h in holdings)
    total_pl = total_mv - total_cost if total_mv else 0.0
    total_pl_pct = (total_pl / total_cost * 100) if total_cost > 0 else 0.0

    day_changes = [r.day_change for r in results if r.day_change is not None]
    total_day = sum(day_changes) if day_changes else None

    # IDR total: IDX positions at face value + US positions converted
    idr_parts: list[float] = []
    for h, r in zip(holdings, results):
        if h.market == "IDX" and r.market_value is not None:
            idr_parts.append(r.market_value)
        elif h.market == "US" and r.market_value_idr is not None:
            idr_parts.append(r.market_value_idr)
    total_idr = sum(idr_parts) if idr_parts else None

    return PortfolioSummary(
        positions=results,
        total_cost_basis=total_cost,
        total_market_value=total_mv,
        total_unrealized_pl=total_pl,
        total_unrealized_pl_pct=total_pl_pct,
        total_day_change=total_day,
        usd_idr_rate=usd_idr_rate,
        total_value_idr=total_idr,
    )
