"""
Tests for src/report/build_brief.py — all network calls mocked.
"""

import dataclasses
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.report.build_brief import (
    _build_macro,
    _build_portfolio,
    _build_signals,
    _load_watchlist,
    _render_brief,
    _scan_tickers,
    build_morning_bundle,
)
from src.portfolio.portfolio import Position, PortfolioSummary, PositionResult
from src.signals.schemas import RiskControl, Signal, SignalType


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_signal(
    ticker: str = "AAPL",
    signal_type: SignalType = SignalType.BUY_WATCHLIST,
    confidence: int = 75,
    market: str = "US",
) -> Signal:
    return Signal(
        ticker=ticker,
        signal_type=signal_type,
        confidence=confidence,
        reasons=["Price is above MA20", "RSI 60.0 — bullish range"],
        invalidation_conditions=["Daily close falls below MA20 (150.00)"],
        risk_control=RiskControl(
            entry_low=148.0,
            entry_high=152.0,
            stop_loss=143.0,
            target=166.0,
            risk_reward=2.3,
            atr=2.5,
        ),
        indicators={"close": 150.0, "rsi": 60.0, "above_ma20": True},
        market=market,
    )


_MACRO_SNAP = {
    "sp500":        {"last": 5304.72, "change_pct": 0.51},
    "nasdaq":       {"last": 16780.0, "change_pct": -0.12},
    "dow":          {"last": 38675.0, "change_pct": 0.56},
    "vix":          {"last": 13.45,   "change_pct": -3.24},
    "oil_wti":      {"last": 78.52,   "change_pct": 0.73},
    "gold":         {"last": 2340.0,  "change_pct": 1.30},
    "us_10y_yield": {"last": 4.472,   "change_pct": -0.64},
    "dxy":          {"last": 104.32,  "change_pct": 0.21},
    "idx_composite":{"last": 7112.0,  "change_pct": 0.38},
    "usd_idr":      {"last": 16245.0, "change_pct": -0.10},
}


def _make_portfolio_dict(n_positions: int = 1) -> dict:
    positions = [
        {
            "ticker": "BBCA.JK", "market": "IDX", "shares": 500,
            "avg_cost": 9200.0, "last_price": 9500.0,
            "market_value": 4_750_000.0, "unrealized_pl": 150_000.0,
            "unrealized_pl_pct": 3.26, "day_change": 50_000.0,
            "day_change_pct": 1.06, "weight_pct": 100.0, "market_value_idr": None,
        }
    ] * n_positions
    return {
        "positions": positions,
        "total_cost_basis": 4_600_000.0,
        "total_market_value": 4_750_000.0,
        "total_unrealized_pl": 150_000.0,
        "total_unrealized_pl_pct": 3.26,
        "total_day_change": 50_000.0,
        "usd_idr_rate": None,
        "total_value_idr": None,
    }


# ── _load_watchlist tests ─────────────────────────────────────────────────────

def test_load_watchlist_reads_tickers(tmp_path):
    f = tmp_path / "wl.csv"
    f.write_text("# comment\nAAPL\nMSFT\n\nNVDA\n", encoding="utf-8")
    result = _load_watchlist(f)
    assert result == ["AAPL", "MSFT", "NVDA"]


def test_load_watchlist_uppercases(tmp_path):
    f = tmp_path / "wl.csv"
    f.write_text("aapl\nmsft\n", encoding="utf-8")
    assert _load_watchlist(f) == ["AAPL", "MSFT"]


def test_load_watchlist_missing_file(tmp_path):
    result = _load_watchlist(tmp_path / "nonexistent.csv")
    assert result == []


def test_load_watchlist_empty_file(tmp_path):
    f = tmp_path / "wl.csv"
    f.write_text("# only comments\n\n", encoding="utf-8")
    assert _load_watchlist(f) == []


# ── _build_macro tests ────────────────────────────────────────────────────────

def test_build_macro_success():
    with patch("src.macro.snapshot.get_macro_snapshot", return_value=_MACRO_SNAP):
        snap, err = _build_macro()
    assert snap is not None
    assert err is None
    assert "sp500" in snap


def test_build_macro_exception_returns_none_and_error_string():
    with patch("src.macro.snapshot.get_macro_snapshot", side_effect=RuntimeError("timeout")):
        snap, err = _build_macro()
    assert snap is None
    assert "timeout" in err


# ── _build_portfolio tests ────────────────────────────────────────────────────

def _make_summary() -> PortfolioSummary:
    pr = PositionResult(
        ticker="BBCA.JK", market="IDX", shares=500, avg_cost=9200.0,
        last_price=9500.0, market_value=4_750_000.0,
        unrealized_pl=150_000.0, unrealized_pl_pct=3.26,
        day_change=50_000.0, day_change_pct=1.06,
        weight_pct=100.0, market_value_idr=None,
    )
    return PortfolioSummary(
        positions=[pr],
        total_cost_basis=4_600_000.0,
        total_market_value=4_750_000.0,
        total_unrealized_pl=150_000.0,
        total_unrealized_pl_pct=3.26,
        total_day_change=50_000.0,
    )


def test_build_portfolio_success(tmp_path):
    csv = tmp_path / "h.csv"
    csv.write_text("ticker,shares,avg_cost,market\nBBCA.JK,500,9200,IDX\n", encoding="utf-8")
    summary = _make_summary()
    with (
        patch("src.portfolio.portfolio.load_holdings", return_value=[MagicMock()]),
        patch("src.portfolio.portfolio.value_portfolio", return_value=summary),
    ):
        pf, err = _build_portfolio(csv)
    assert err is None
    assert pf is not None
    assert pf["total_market_value"] == pytest.approx(4_750_000.0)
    assert isinstance(pf["positions"], list)


def test_build_portfolio_file_not_found(tmp_path):
    pf, err = _build_portfolio(tmp_path / "missing.csv")
    assert pf is None
    assert err is not None
    assert "not found" in err.lower() or "missing" in err.lower()


def test_build_portfolio_empty_holdings(tmp_path):
    csv = tmp_path / "h.csv"
    csv.write_text("ticker,shares,avg_cost,market\n", encoding="utf-8")
    with patch("src.portfolio.portfolio.load_holdings", return_value=[]):
        pf, err = _build_portfolio(csv)
    assert err is None
    assert pf["total_market_value"] == 0.0
    assert pf["positions"] == []


# ── _scan_tickers tests ───────────────────────────────────────────────────────

def test_scan_tickers_returns_actionable_only():
    buy_signal  = _make_signal("AAPL", SignalType.BUY_WATCHLIST)
    hold_signal = _make_signal("MSFT", SignalType.HOLD)
    avoid_signal = _make_signal("NVDA", SignalType.AVOID)

    import pandas as pd
    fake_df = pd.DataFrame({"open": [1]*60, "high": [1]*60, "low": [1]*60,
                            "close": [1]*60, "volume": [1]*60})

    signals_by_ticker = {
        "AAPL": buy_signal,
        "MSFT": hold_signal,
        "NVDA": avoid_signal,
    }

    def fake_generate(ticker, indicators, market="US"):
        return signals_by_ticker[ticker]

    with (
        patch("src.data.yfinance_provider.YFinanceProvider.get_ohlcv", return_value=fake_df),
        patch("src.indicators.technicals.compute_indicators", return_value={"close": 150.0, "rsi": 60.0}),
        patch("src.signals.engine.generate_signal", side_effect=fake_generate),
    ):
        results, errors = _scan_tickers([("AAPL", "US"), ("MSFT", "US"), ("NVDA", "US")])

    assert len(results) == 1
    assert results[0]["ticker"] == "AAPL"
    assert results[0]["signal_type"] == "BUY_WATCHLIST"
    assert errors == []


def test_scan_tickers_empty_ohlcv_returns_error():
    import pandas as pd
    with patch("src.data.yfinance_provider.YFinanceProvider.get_ohlcv", return_value=pd.DataFrame()):
        results, errors = _scan_tickers([("BADTICK", "US")])
    assert results == []
    assert len(errors) == 1
    assert "BADTICK" in errors[0]


def test_scan_tickers_empty_pairs():
    results, errors = _scan_tickers([])
    assert results == []
    assert errors == []


def test_scan_tickers_exception_captured():
    import pandas as pd
    fake_df = pd.DataFrame({"open": [1]*60, "high": [1]*60, "low": [1]*60,
                            "close": [1]*60, "volume": [1]*60})
    with (
        patch("src.data.yfinance_provider.YFinanceProvider.get_ohlcv", return_value=fake_df),
        patch("src.indicators.technicals.compute_indicators", side_effect=ValueError("boom")),
    ):
        results, errors = _scan_tickers([("AAPL", "US")])
    assert results == []
    assert any("AAPL" in e and "boom" in e for e in errors)


# ── build_morning_bundle integration tests ────────────────────────────────────

def _mock_sections(macro=None, portfolio=None, signals=None, sig_errors=None):
    """Context manager that patches all three section builders."""
    macro     = macro     or _MACRO_SNAP
    portfolio = portfolio or _make_portfolio_dict()
    signals   = signals   or {"portfolio": [], "watchlist": []}
    sig_errors = sig_errors or {}

    return (
        patch("src.report.build_brief._build_macro",    return_value=(macro, None)),
        patch("src.report.build_brief._build_portfolio", return_value=(portfolio, None)),
        patch("src.report.build_brief._build_signals",  return_value=(signals, sig_errors)),
    )


def test_bundle_writes_json_and_md(tmp_path):
    m, p, s = _mock_sections()
    with m, p, s:
        bundle = build_morning_bundle(
            run_date=date(2026, 6, 4),
            holdings_path=tmp_path / "h.csv",
            out_dir=tmp_path / "reports",
        )

    json_file = tmp_path / "reports" / "morning_data_2026-06-04.json"
    md_file   = tmp_path / "reports" / "morning_brief_2026-06-04.md"

    assert json_file.exists(), "JSON file not written"
    assert md_file.exists(),   "Markdown brief not written"


def test_bundle_json_is_valid_and_has_required_keys(tmp_path):
    m, p, s = _mock_sections()
    with m, p, s:
        build_morning_bundle(
            run_date=date(2026, 6, 4),
            holdings_path=tmp_path / "h.csv",
            out_dir=tmp_path / "reports",
        )

    data = json.loads((tmp_path / "reports" / "morning_data_2026-06-04.json").read_text())
    assert data["date"] == "2026-06-04"
    assert "generated_at" in data
    assert "macro" in data
    assert "portfolio" in data
    assert "signals" in data
    assert "errors" in data
    assert set(data["signals"].keys()) == {"portfolio", "watchlist"}


def test_bundle_returns_dict_with_same_content(tmp_path):
    m, p, s = _mock_sections()
    with m, p, s:
        bundle = build_morning_bundle(
            run_date=date(2026, 6, 4),
            holdings_path=tmp_path / "h.csv",
            out_dir=tmp_path / "reports",
        )

    assert bundle["date"] == "2026-06-04"
    assert bundle["macro"] == _MACRO_SNAP
    assert bundle["portfolio"]["total_market_value"] == pytest.approx(4_750_000.0)


def test_bundle_macro_failure_produces_null_macro_and_error_key(tmp_path):
    with (
        patch("src.report.build_brief._build_macro",    return_value=(None, "timeout")),
        patch("src.report.build_brief._build_portfolio", return_value=(_make_portfolio_dict(), None)),
        patch("src.report.build_brief._build_signals",  return_value=({"portfolio": [], "watchlist": []}, {})),
    ):
        bundle = build_morning_bundle(
            run_date=date(2026, 6, 4),
            holdings_path=tmp_path / "h.csv",
            out_dir=tmp_path / "reports",
        )

    assert bundle["macro"] is None
    assert "macro" in bundle["errors"]
    assert bundle["portfolio"] is not None   # portfolio still present


def test_bundle_portfolio_failure_still_writes_macro(tmp_path):
    with (
        patch("src.report.build_brief._build_macro",    return_value=(_MACRO_SNAP, None)),
        patch("src.report.build_brief._build_portfolio", return_value=(None, "FileNotFoundError")),
        patch("src.report.build_brief._build_signals",  return_value=({"portfolio": [], "watchlist": []}, {})),
    ):
        bundle = build_morning_bundle(
            run_date=date(2026, 6, 4),
            holdings_path=tmp_path / "h.csv",
            out_dir=tmp_path / "reports",
        )

    assert bundle["macro"] == _MACRO_SNAP
    assert bundle["portfolio"] is None
    assert "portfolio" in bundle["errors"]


def test_bundle_signals_errors_appear_in_errors_key(tmp_path):
    sig_errs = {"portfolio": [], "watchlist": ["NVDA: no data", "TSLA: timeout"]}
    with (
        patch("src.report.build_brief._build_macro",    return_value=(_MACRO_SNAP, None)),
        patch("src.report.build_brief._build_portfolio", return_value=(_make_portfolio_dict(), None)),
        patch("src.report.build_brief._build_signals",  return_value=({"portfolio": [], "watchlist": []}, sig_errs)),
    ):
        bundle = build_morning_bundle(
            run_date=date(2026, 6, 4),
            holdings_path=tmp_path / "h.csv",
            out_dir=tmp_path / "reports",
        )

    assert "signals" in bundle["errors"]
    assert bundle["errors"]["signals"]["watchlist"] == ["NVDA: no data", "TSLA: timeout"]


def test_bundle_no_errors_key_is_empty_dict(tmp_path):
    m, p, s = _mock_sections()
    with m, p, s:
        bundle = build_morning_bundle(
            run_date=date(2026, 6, 4),
            holdings_path=tmp_path / "h.csv",
            out_dir=tmp_path / "reports",
        )
    assert bundle["errors"] == {}


def test_bundle_actionable_signals_present_in_json(tmp_path):
    buy = _make_signal("AAPL", SignalType.BUY_WATCHLIST, confidence=80)
    sell = _make_signal("TSLA", SignalType.SELL_WARNING, confidence=70)
    signals = {
        "portfolio": [buy.model_dump(mode="json")],
        "watchlist": [sell.model_dump(mode="json")],
    }
    with (
        patch("src.report.build_brief._build_macro",    return_value=(_MACRO_SNAP, None)),
        patch("src.report.build_brief._build_portfolio", return_value=(_make_portfolio_dict(), None)),
        patch("src.report.build_brief._build_signals",  return_value=(signals, {})),
    ):
        build_morning_bundle(
            run_date=date(2026, 6, 4),
            holdings_path=tmp_path / "h.csv",
            out_dir=tmp_path / "reports",
        )

    data = json.loads((tmp_path / "reports" / "morning_data_2026-06-04.json").read_text())
    assert data["signals"]["portfolio"][0]["ticker"] == "AAPL"
    assert data["signals"]["portfolio"][0]["signal_type"] == "BUY_WATCHLIST"
    assert data["signals"]["watchlist"][0]["ticker"] == "TSLA"


# ── _render_brief tests ───────────────────────────────────────────────────────

_UNSET = object()  # sentinel so callers can explicitly pass None


def _make_bundle(
    macro=_UNSET,
    portfolio=_UNSET,
    signals=_UNSET,
    errors=_UNSET,
) -> dict:
    return {
        "date": "2026-06-04",
        "generated_at": "2026-06-04T07:00:00+00:00",
        "macro":     _MACRO_SNAP          if macro     is _UNSET else macro,
        "portfolio": _make_portfolio_dict() if portfolio is _UNSET else portfolio,
        "signals":   {"portfolio": [], "watchlist": []} if signals is _UNSET else signals,
        "errors":    {}                   if errors    is _UNSET else errors,
    }


def test_render_brief_contains_date():
    text = _render_brief(_make_bundle())
    assert "2026-06-04" in text


def test_render_brief_macro_section():
    text = _render_brief(_make_bundle())
    assert "Macro Snapshot" in text
    assert "S&P 500" in text


def test_render_brief_portfolio_section_with_data():
    text = _render_brief(_make_bundle())
    assert "Portfolio" in text
    assert "BBCA.JK" in text


def test_render_brief_null_macro_shows_unavailable():
    text = _render_brief(_make_bundle(macro=None))
    assert "unavailable" in text.lower()


def test_render_brief_null_portfolio_shows_unavailable():
    text = _render_brief(_make_bundle(portfolio=None))
    assert "unavailable" in text.lower()


def test_render_brief_no_signals_shows_message():
    text = _render_brief(_make_bundle(signals={"portfolio": [], "watchlist": []}))
    assert "No actionable signals" in text


def test_render_brief_signals_rendered():
    buy = _make_signal("AAPL", SignalType.BUY_WATCHLIST, confidence=80)
    signals = {"portfolio": [buy.model_dump(mode="json")], "watchlist": []}
    text = _render_brief(_make_bundle(signals=signals))
    assert "AAPL" in text
    assert "BUY_WATCHLIST" in text
    assert "80%" in text


def test_render_brief_errors_section():
    text = _render_brief(_make_bundle(errors={"macro": "timeout"}))
    assert "Errors" in text
    assert "timeout" in text


def test_render_brief_no_errors_section_when_clean():
    text = _render_brief(_make_bundle(errors={}))
    assert "## Errors" not in text


def test_render_brief_footer_contains_generated_at():
    text = _render_brief(_make_bundle())
    assert "2026-06-04T07:00:00+00:00" in text
    assert "No LLM" in text
