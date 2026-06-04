"""
Tests for src/report/send_brief.py — notifier and bundle building are mocked.
"""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.report.send_brief import (
    WHATSAPP_LIMIT,
    _DISCLAIMER,
    _fmt_chg,
    _fmt_macro_section,
    _fmt_portfolio_section,
    _fmt_price,
    _fmt_signals_section,
    compose_morning_messages,
    send_morning_brief,
)
from src.signals.schemas import RiskControl, Signal, SignalType


# ── Fixtures ───────────────────────────────────────────────────────────────────

_MACRO = {
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

_PORTFOLIO = {
    "positions": [
        {
            "ticker": "BBCA.JK", "market": "IDX", "shares": 500,
            "avg_cost": 9200.0, "last_price": 9500.0, "market_value": 4_750_000.0,
            "unrealized_pl": 150_000.0, "unrealized_pl_pct": 3.26,
            "day_change": 50_000.0, "day_change_pct": 1.06,
            "weight_pct": 70.0, "market_value_idr": None,
        },
        {
            "ticker": "AAPL", "market": "US", "shares": 10,
            "avg_cost": 175.0, "last_price": 200.0, "market_value": 2000.0,
            "unrealized_pl": 250.0, "unrealized_pl_pct": 14.29,
            "day_change": 50.0, "day_change_pct": 2.56,
            "weight_pct": 30.0, "market_value_idr": 32_000_000.0,
        },
    ],
    "total_cost_basis": 6_350_000.0,
    "total_market_value": 4_752_000.0,
    "total_unrealized_pl": 150_250.0,
    "total_unrealized_pl_pct": 2.37,
    "total_day_change": 50_050.0,
    "usd_idr_rate": 16_000.0,
    "total_value_idr": 36_750_000.0,
}

def _make_signal_dict(
    ticker: str = "AAPL",
    signal_type: str = "BUY_WATCHLIST",
    confidence: int = 75,
    market: str = "US",
    close: float = 200.0,
) -> dict:
    s = Signal(
        ticker=ticker,
        signal_type=SignalType(signal_type),
        confidence=confidence,
        reasons=["Price is above MA20", "RSI 60 — bullish"],
        invalidation_conditions=["Daily close below MA20 (190.00)"],
        risk_control=RiskControl(
            entry_low=198.0, entry_high=202.0,
            stop_loss=193.0, target=214.0,
            risk_reward=2.3, atr=2.5,
        ),
        indicators={"close": close, "rsi": 60.0},
        market=market,
    )
    return s.model_dump(mode="json")


def _make_bundle(
    macro=None, portfolio=None, signals=None, date_str="2026-06-04"
) -> dict:
    return {
        "date": date_str,
        "generated_at": "2026-06-04T07:00:00+00:00",
        "macro":     macro     if macro     is not None else _MACRO,
        "portfolio": portfolio if portfolio is not None else _PORTFOLIO,
        "signals":   signals   if signals   is not None else {"portfolio": [], "watchlist": []},
        "errors": {},
    }


def _make_settings(dry_run: bool = True):
    s = MagicMock()
    s.dry_run = dry_run
    s.whatsapp_provider = "meta"
    return s


# ── _fmt_price tests ──────────────────────────────────────────────────────────

def test_fmt_price_none():
    assert _fmt_price(None) == "N/A"


def test_fmt_price_large():
    assert _fmt_price(9500.0) == "9,500"


def test_fmt_price_small():
    assert _fmt_price(78.52) == "78.52"


def test_fmt_price_sub_one():
    result = _fmt_price(0.0042)
    assert "0.004" in result


# ── _fmt_chg tests ────────────────────────────────────────────────────────────

def test_fmt_chg_positive():
    result = _fmt_chg(0.51)
    assert "+0.51%" in result
    assert "▲" in result


def test_fmt_chg_negative():
    result = _fmt_chg(-3.24)
    assert "-3.24%" in result
    assert "▼" in result


def test_fmt_chg_none():
    assert _fmt_chg(None) == "N/A"


# ── _fmt_macro_section tests ──────────────────────────────────────────────────

def test_macro_section_contains_sp500():
    text = _fmt_macro_section(_MACRO)
    assert "S&P 500" in text
    # 5304.72 rounds to 5,305 via _fmt_price (uses :,.0f)
    assert "5,305" in text


def test_macro_section_contains_indonesia():
    text = _fmt_macro_section(_MACRO)
    assert "Indonesia" in text
    assert "IDX" in text
    assert "USD/IDR" in text


def test_macro_section_positive_has_up_arrow():
    text = _fmt_macro_section(_MACRO)
    assert "▲" in text


def test_macro_section_negative_has_down_arrow():
    text = _fmt_macro_section(_MACRO)
    assert "▼" in text


def test_macro_section_none_shows_unavailable():
    text = _fmt_macro_section(None)
    assert "unavailable" in text.lower()


# ── _fmt_portfolio_section tests ──────────────────────────────────────────────

def test_portfolio_section_shows_total_value():
    text = _fmt_portfolio_section(_PORTFOLIO)
    assert "4,752,000" in text or "4752000" in text.replace(",", "")


def test_portfolio_section_shows_pl():
    text = _fmt_portfolio_section(_PORTFOLIO)
    assert "+150,250" in text or "150,250" in text


def test_portfolio_section_shows_movers():
    text = _fmt_portfolio_section(_PORTFOLIO)
    assert "BBCA.JK" in text
    assert "AAPL" in text


def test_portfolio_section_sorts_movers_by_abs_change():
    # AAPL has +2.56%, BBCA.JK has +1.06% — AAPL should appear first
    text = _fmt_portfolio_section(_PORTFOLIO)
    aapl_idx  = text.find("AAPL")
    bbca_idx  = text.find("BBCA.JK")
    # AAPL has bigger day_change_pct, so it comes first in movers
    assert aapl_idx < bbca_idx


def test_portfolio_section_none_shows_unavailable():
    text = _fmt_portfolio_section(None)
    assert "unavailable" in text.lower()


def test_portfolio_section_idr_total_shown():
    text = _fmt_portfolio_section(_PORTFOLIO)
    assert "36,750,000" in text


# ── _fmt_signals_section tests ────────────────────────────────────────────────

def test_signals_section_buy_header():
    signals = {"portfolio": [_make_signal_dict("AAPL", "BUY_WATCHLIST")], "watchlist": []}
    text = _fmt_signals_section(signals)
    assert "Buy Watchlist" in text
    assert "AAPL" in text


def test_signals_section_sell_header():
    signals = {"portfolio": [], "watchlist": [_make_signal_dict("TSLA", "SELL_WARNING")]}
    text = _fmt_signals_section(signals)
    assert "Sell Warnings" in text
    assert "TSLA" in text


def test_signals_section_shows_entry_stop_target():
    signals = {"portfolio": [_make_signal_dict("AAPL", "BUY_WATCHLIST")], "watchlist": []}
    text = _fmt_signals_section(signals)
    assert "Entry" in text
    assert "Stop" in text
    assert "Tgt" in text
    assert "R/R" in text


def test_signals_section_shows_reason():
    signals = {"portfolio": [_make_signal_dict("AAPL", "BUY_WATCHLIST")], "watchlist": []}
    text = _fmt_signals_section(signals)
    assert "above MA20" in text or "MA20" in text


def test_signals_section_empty_shows_no_signals_message():
    text = _fmt_signals_section({"portfolio": [], "watchlist": []})
    assert "no actionable signals" in text.lower()


def test_signals_section_max_per_type_truncates():
    many_buys = [_make_signal_dict(f"T{i}", "BUY_WATCHLIST", confidence=80-i) for i in range(10)]
    signals = {"portfolio": many_buys, "watchlist": []}
    text = _fmt_signals_section(signals, max_per_type=3)
    # Count bullet points for tickers: should have at most 3
    tickers_shown = [f"T{i}" in text for i in range(10)]
    assert sum(tickers_shown) <= 3


def test_signals_section_sorted_by_confidence():
    signals = {
        "portfolio": [
            _make_signal_dict("LOW",  "BUY_WATCHLIST", confidence=60),
            _make_signal_dict("HIGH", "BUY_WATCHLIST", confidence=90),
        ],
        "watchlist": [],
    }
    text = _fmt_signals_section(signals)
    assert text.index("HIGH") < text.index("LOW")


def test_signals_section_combines_portfolio_and_watchlist():
    signals = {
        "portfolio": [_make_signal_dict("BBCA.JK", "BUY_WATCHLIST", market="IDX")],
        "watchlist": [_make_signal_dict("AAPL",    "BUY_WATCHLIST", market="US")],
    }
    text = _fmt_signals_section(signals)
    assert "BBCA.JK" in text
    assert "AAPL" in text


# ── compose_morning_messages tests ────────────────────────────────────────────

def test_compose_returns_list():
    msgs = compose_morning_messages(_make_bundle())
    assert isinstance(msgs, list)
    assert len(msgs) >= 1


def test_compose_single_message_for_typical_bundle():
    msgs = compose_morning_messages(_make_bundle())
    assert len(msgs) == 1
    assert len(msgs[0]) <= WHATSAPP_LIMIT


def test_compose_message_has_header():
    msgs = compose_morning_messages(_make_bundle())
    full = "\n".join(msgs)
    assert "Morning Brief" in full


def test_compose_message_has_disclaimer():
    msgs = compose_morning_messages(_make_bundle())
    full = "\n".join(msgs)
    assert "Not financial advice" in full
    assert "No trades" in full


def test_compose_message_has_macro():
    msgs = compose_morning_messages(_make_bundle())
    full = "\n".join(msgs)
    assert "S&P 500" in full
    assert "IDX" in full


def test_compose_message_has_portfolio():
    msgs = compose_morning_messages(_make_bundle())
    full = "\n".join(msgs)
    assert "Portfolio" in full
    assert "BBCA.JK" in full


def test_compose_splits_when_signals_overflow(tmp_path):
    # Create enough signals to force a split
    many_signals = [
        _make_signal_dict(f"TICK{i:03}", "BUY_WATCHLIST", confidence=90)
        for i in range(30)
    ]
    bundle = _make_bundle(signals={"portfolio": many_signals, "watchlist": []})
    msgs = compose_morning_messages(bundle)
    # May be 1 or 2; if 2, each must be within limit
    for msg in msgs:
        assert len(msg) <= WHATSAPP_LIMIT


def test_compose_all_none_sections_does_not_crash():
    bundle = {
        "date": "2026-06-04",
        "generated_at": "2026-06-04T07:00:00+00:00",
        "macro": None,
        "portfolio": None,
        "signals": {"portfolio": [], "watchlist": []},
        "errors": {},
    }
    msgs = compose_morning_messages(bundle)
    assert len(msgs) >= 1
    assert "Morning Brief" in msgs[0]


# ── send_morning_brief tests ──────────────────────────────────────────────────

def test_send_dry_run_returns_true(tmp_path):
    settings = _make_settings(dry_run=True)
    bundle = _make_bundle()
    result = send_morning_brief(bundle=bundle, settings=settings, out_dir=tmp_path)
    assert result is True


def test_send_dry_run_does_not_call_notifier(tmp_path):
    settings = _make_settings(dry_run=True)
    bundle = _make_bundle()
    with patch("src.report.send_brief.get_notifier") as mock_get:
        send_morning_brief(bundle=bundle, settings=settings, out_dir=tmp_path)
    mock_get.assert_not_called()


def test_send_live_calls_notifier_send(tmp_path):
    settings = _make_settings(dry_run=False)
    mock_notifier = MagicMock()
    mock_notifier.send.return_value = True
    bundle = _make_bundle()

    with patch("src.report.send_brief.get_notifier", return_value=mock_notifier):
        result = send_morning_brief(bundle=bundle, settings=settings, out_dir=tmp_path)

    assert result is True
    assert mock_notifier.send.called


def test_send_multi_message_calls_send_for_each(tmp_path):
    settings = _make_settings(dry_run=False)
    mock_notifier = MagicMock()
    mock_notifier.send.return_value = True

    # Force two messages by patching compose
    with (
        patch("src.report.send_brief.compose_morning_messages", return_value=["msg1", "msg2"]),
        patch("src.report.send_brief.get_notifier", return_value=mock_notifier),
    ):
        result = send_morning_brief(
            bundle=_make_bundle(), settings=settings, out_dir=tmp_path
        )

    assert mock_notifier.send.call_count == 2
    assert result is True


def test_send_partial_failure_returns_false(tmp_path):
    settings = _make_settings(dry_run=False)
    mock_notifier = MagicMock()
    # First send succeeds, second fails
    mock_notifier.send.side_effect = [True, False]

    with (
        patch("src.report.send_brief.compose_morning_messages", return_value=["msg1", "msg2"]),
        patch("src.report.send_brief.get_notifier", return_value=mock_notifier),
    ):
        result = send_morning_brief(
            bundle=_make_bundle(), settings=settings, out_dir=tmp_path
        )

    assert result is False


def test_send_saves_full_text_to_file(tmp_path):
    settings = _make_settings(dry_run=True)
    bundle = _make_bundle()
    send_morning_brief(bundle=bundle, settings=settings, out_dir=tmp_path)
    saved = list(tmp_path.glob("morning_whatsapp_*.txt"))
    assert len(saved) == 1
    content = saved[0].read_text(encoding="utf-8")
    assert "Morning Brief" in content


def test_send_builds_bundle_when_not_supplied(tmp_path):
    settings = _make_settings(dry_run=True)
    fake_bundle = _make_bundle()

    with patch("src.report.send_brief.build_morning_bundle", return_value=fake_bundle) as mock_build:
        send_morning_brief(settings=settings, out_dir=tmp_path)

    mock_build.assert_called_once()


def test_send_uses_prebuilt_bundle_without_rebuilding(tmp_path):
    settings = _make_settings(dry_run=True)
    bundle = _make_bundle()

    with patch("src.report.send_brief.build_morning_bundle") as mock_build:
        send_morning_brief(bundle=bundle, settings=settings, out_dir=tmp_path)

    mock_build.assert_not_called()


def test_send_file_named_with_bundle_date(tmp_path):
    settings = _make_settings(dry_run=True)
    bundle = _make_bundle(date_str="2026-07-15")
    send_morning_brief(bundle=bundle, settings=settings, out_dir=tmp_path)
    assert (tmp_path / "morning_whatsapp_2026-07-15.txt").exists()
