"""
Tests for src/portfolio/portfolio.py.

All yfinance network calls are mocked — tests run offline and deterministically.
"""

import csv
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.portfolio.portfolio import (
    Position,
    PortfolioSummary,
    PositionResult,
    load_holdings,
    value_portfolio,
)


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _csv(rows: list[dict], comment: str | None = None) -> Path:
    """Write a temporary holdings CSV and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8"
    )
    if comment:
        tmp.write(f"# {comment}\n")
    writer = csv.DictWriter(tmp, fieldnames=["ticker", "shares", "avg_cost", "market"])
    writer.writeheader()
    writer.writerows(rows)
    tmp.close()
    return Path(tmp.name)


def _mock_prices(price_map: dict[str, tuple[float, float]]):
    """
    Return a patcher that replaces _fetch_last_prices with a dict-returning stub.
    price_map: {ticker: (last_price, prev_close)}
    """
    return patch(
        "src.portfolio.portfolio._fetch_last_prices",
        return_value=price_map,
    )


def _mock_usd_idr(rate: float | None):
    return patch("src.portfolio.portfolio._fetch_usd_idr", return_value=rate)


# ── load_holdings tests ───────────────────────────────────────────────────────

def test_load_holdings_basic():
    path = _csv([
        {"ticker": "BBCA.JK", "shares": 500, "avg_cost": 9200, "market": "IDX"},
        {"ticker": "AAPL",    "shares": 10,  "avg_cost": 175,  "market": "US"},
    ])
    holdings = load_holdings(path)
    assert len(holdings) == 2
    assert holdings[0].ticker == "BBCA.JK"
    assert holdings[0].shares == 500
    assert holdings[0].avg_cost == 9200
    assert holdings[0].market == "IDX"
    assert holdings[1].ticker == "AAPL"
    assert holdings[1].market == "US"


def test_load_holdings_skips_comments_and_blank_lines():
    path = _csv(
        [{"ticker": "TLKM.JK", "shares": 1000, "avg_cost": 3800, "market": "IDX"}],
        comment="Sample holdings",
    )
    holdings = load_holdings(path)
    assert len(holdings) == 1
    assert holdings[0].ticker == "TLKM.JK"


def test_load_holdings_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_holdings("/nonexistent/path/holdings.csv")


def test_load_holdings_normalises_ticker_case():
    path = _csv([{"ticker": "aapl", "shares": 5, "avg_cost": 150, "market": "us"}])
    holdings = load_holdings(path)
    assert holdings[0].ticker == "AAPL"
    assert holdings[0].market == "US"


# ── Position math tests (pure, no mocks needed) ───────────────────────────────

def test_position_cost_basis():
    pos = Position(ticker="AAPL", shares=10, avg_cost=150.0, market="US")
    assert pos.cost_basis == 1500.0


def test_position_market_value_and_pl():
    pos = Position(ticker="AAPL", shares=10, avg_cost=150.0, market="US")
    pos.last_price = 180.0
    assert pos.market_value == 1800.0
    assert pos.unrealized_pl == pytest.approx(300.0)
    assert pos.unrealized_pl_pct == pytest.approx(20.0)


def test_position_unrealized_pl_loss():
    pos = Position(ticker="AAPL", shares=10, avg_cost=200.0, market="US")
    pos.last_price = 180.0
    assert pos.unrealized_pl == pytest.approx(-200.0)
    assert pos.unrealized_pl_pct == pytest.approx(-10.0)


def test_position_day_change():
    pos = Position(ticker="AAPL", shares=10, avg_cost=150.0, market="US")
    pos.last_price = 182.0
    pos.prev_close = 180.0
    assert pos.day_change == pytest.approx(20.0)   # 2 * 10
    assert pos.day_change_pct == pytest.approx(2.0 / 180.0 * 100)


def test_position_none_when_no_price():
    pos = Position(ticker="AAPL", shares=10, avg_cost=150.0, market="US")
    assert pos.market_value is None
    assert pos.unrealized_pl is None
    assert pos.unrealized_pl_pct is None
    assert pos.day_change is None


# ── value_portfolio integration tests ────────────────────────────────────────

def test_value_portfolio_empty():
    summary = value_portfolio([])
    assert summary.total_market_value == 0.0
    assert summary.total_cost_basis == 0.0
    assert summary.positions == []


def test_value_portfolio_single_idx_position():
    pos = Position(ticker="BBCA.JK", shares=500, avg_cost=9_200.0, market="IDX")
    with _mock_prices({"BBCA.JK": (9_500.0, 9_400.0)}):
        summary = value_portfolio([pos])

    assert len(summary.positions) == 1
    r = summary.positions[0]

    assert r.last_price == pytest.approx(9_500.0)
    assert r.market_value == pytest.approx(500 * 9_500.0)
    assert r.unrealized_pl == pytest.approx(500 * (9_500.0 - 9_200.0))
    assert r.unrealized_pl_pct == pytest.approx(300.0 / 9_200.0 * 100)
    assert r.day_change == pytest.approx(500 * (9_500.0 - 9_400.0))
    assert r.weight_pct == pytest.approx(100.0)
    assert r.market_value_idr is None   # IDX — no conversion needed


def test_value_portfolio_us_position_with_idr_conversion():
    pos = Position(ticker="AAPL", shares=10, avg_cost=175.0, market="US")
    usd_idr = 16_000.0
    with _mock_prices({"AAPL": (200.0, 195.0)}), _mock_usd_idr(usd_idr):
        summary = value_portfolio([pos])

    r = summary.positions[0]
    assert r.last_price == pytest.approx(200.0)
    assert r.market_value == pytest.approx(2_000.0)
    assert r.market_value_idr == pytest.approx(2_000.0 * usd_idr)
    assert summary.usd_idr_rate == pytest.approx(usd_idr)
    assert summary.total_value_idr == pytest.approx(2_000.0 * usd_idr)


def test_value_portfolio_mixed_idx_and_us():
    holdings = [
        Position(ticker="BBCA.JK", shares=500,  avg_cost=9_200.0, market="IDX"),
        Position(ticker="AAPL",    shares=10,   avg_cost=175.0,   market="US"),
    ]
    prices = {
        "BBCA.JK": (9_500.0, 9_400.0),
        "AAPL":    (200.0, 195.0),
    }
    usd_idr = 16_000.0
    with _mock_prices(prices), _mock_usd_idr(usd_idr):
        summary = value_portfolio(holdings)

    idx_mv = 500 * 9_500.0    # 4_750_000 IDR
    us_mv  = 10  * 200.0      # 2_000 USD
    total_mv = idx_mv + us_mv

    assert summary.total_market_value == pytest.approx(total_mv)
    assert summary.total_cost_basis == pytest.approx(500 * 9_200.0 + 10 * 175.0)

    # Weights
    bbca_result = next(r for r in summary.positions if r.ticker == "BBCA.JK")
    aapl_result = next(r for r in summary.positions if r.ticker == "AAPL")
    assert bbca_result.weight_pct == pytest.approx(idx_mv / total_mv * 100)
    assert aapl_result.weight_pct == pytest.approx(us_mv / total_mv * 100)

    # IDR total = IDX mv (native IDR) + US mv * rate
    expected_idr = idx_mv + us_mv * usd_idr
    assert summary.total_value_idr == pytest.approx(expected_idr)


def test_value_portfolio_totals_math():
    holdings = [
        Position(ticker="BBCA.JK", shares=100, avg_cost=9_000.0, market="IDX"),
        Position(ticker="TLKM.JK", shares=200, avg_cost=4_000.0, market="IDX"),
    ]
    prices = {
        "BBCA.JK": (10_000.0, 9_800.0),
        "TLKM.JK": (3_500.0,  3_600.0),
    }
    with _mock_prices(prices):
        summary = value_portfolio(holdings)

    cost     = 100 * 9_000.0 + 200 * 4_000.0       # 1_700_000
    mv       = 100 * 10_000.0 + 200 * 3_500.0       # 1_700_000
    pl       = mv - cost                             # 0
    pl_pct   = pl / cost * 100                       # 0.0
    day_chg  = 100 * (10_000 - 9_800) + 200 * (3_500 - 3_600)  # 20_000 - 20_000 = 0

    assert summary.total_cost_basis      == pytest.approx(cost)
    assert summary.total_market_value    == pytest.approx(mv)
    assert summary.total_unrealized_pl   == pytest.approx(pl)
    assert summary.total_unrealized_pl_pct == pytest.approx(pl_pct)
    assert summary.total_day_change      == pytest.approx(day_chg)


def test_value_portfolio_missing_price_handled():
    holdings = [
        Position(ticker="BBCA.JK", shares=500, avg_cost=9_200.0, market="IDX"),
        Position(ticker="UNKNOWN",  shares=100, avg_cost=5_000.0, market="IDX"),
    ]
    # UNKNOWN returns no price
    with _mock_prices({"BBCA.JK": (9_500.0, 9_400.0)}):
        summary = value_portfolio(holdings)

    unknown = next(r for r in summary.positions if r.ticker == "UNKNOWN")
    assert unknown.last_price is None
    assert unknown.market_value is None
    assert unknown.weight_pct is None
    # Total market value only counts priced positions
    assert summary.total_market_value == pytest.approx(500 * 9_500.0)


def test_value_portfolio_usd_idr_override():
    pos = Position(ticker="AAPL", shares=5, avg_cost=100.0, market="US")
    with _mock_prices({"AAPL": (110.0, 108.0)}):
        # Pass rate explicitly — _fetch_usd_idr should NOT be called
        with patch("src.portfolio.portfolio._fetch_usd_idr") as mock_rate:
            summary = value_portfolio([pos], usd_idr_rate=15_500.0)
            mock_rate.assert_not_called()

    r = summary.positions[0]
    assert r.market_value_idr == pytest.approx(5 * 110.0 * 15_500.0)
