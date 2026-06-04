"""Tests for src/macro/snapshot.py — all network calls mocked."""

from unittest.mock import patch

import pytest

from src.macro.snapshot import get_macro_snapshot, get_macro_summary_text


# ── Helpers ───────────────────────────────────────────────────────────────────

# Realistic quote pairs: {ticker: (last, prev_close)}
_QUOTES: dict[str, tuple[float, float]] = {
    "^GSPC":    (5_304.72, 5_277.51),
    "^IXIC":    (16_780.00, 16_801.54),
    "^DJI":     (38_675.68, 38_460.92),
    "^VIX":     (13.45, 13.90),
    "CL=F":     (78.52, 77.95),
    "GC=F":     (2_340.0, 2_310.0),
    "^TNX":     (4.472, 4.501),
    "DX-Y.NYB": (104.32, 104.10),
    "^JKSE":    (7_112.0, 7_085.0),
    "IDR=X":    (16_245.0, 16_262.0),
}


def _mock_fetch(quotes: dict | None = None):
    return patch(
        "src.macro.snapshot._fetch_quotes",
        return_value=quotes if quotes is not None else _QUOTES,
    )


# ── get_macro_snapshot tests ──────────────────────────────────────────────────

def test_snapshot_returns_all_keys():
    with _mock_fetch():
        snap = get_macro_snapshot()

    expected_keys = {
        "sp500", "nasdaq", "dow", "vix",
        "oil_wti", "gold", "us_10y_yield", "dxy",
        "idx_composite", "usd_idr",
    }
    assert set(snap.keys()) == expected_keys


def test_snapshot_each_entry_has_last_and_change_pct():
    with _mock_fetch():
        snap = get_macro_snapshot()

    for key, entry in snap.items():
        assert "last" in entry,       f"{key} missing 'last'"
        assert "change_pct" in entry, f"{key} missing 'change_pct'"


def test_snapshot_sp500_values():
    with _mock_fetch():
        snap = get_macro_snapshot()

    assert snap["sp500"]["last"] == pytest.approx(5_304.72)
    expected_chg = round((5_304.72 - 5_277.51) / 5_277.51 * 100, 2)
    assert snap["sp500"]["change_pct"] == pytest.approx(expected_chg)


def test_snapshot_vix_values():
    with _mock_fetch():
        snap = get_macro_snapshot()

    assert snap["vix"]["last"] == pytest.approx(13.45)
    expected_chg = round((13.45 - 13.90) / 13.90 * 100, 2)
    assert snap["vix"]["change_pct"] == pytest.approx(expected_chg)


def test_snapshot_usd_idr_values():
    with _mock_fetch():
        snap = get_macro_snapshot()

    assert snap["usd_idr"]["last"] == pytest.approx(16_245.0)
    # IDR strengthened (rate fell) → negative change
    assert snap["usd_idr"]["change_pct"] < 0


def test_snapshot_missing_ticker_returns_none():
    # Only supply a subset of quotes — the rest should gracefully return None
    partial = {"^GSPC": (5_304.72, 5_277.51)}
    with _mock_fetch(partial):
        snap = get_macro_snapshot()

    assert snap["sp500"]["last"] is not None
    assert snap["nasdaq"]["last"] is None
    assert snap["nasdaq"]["change_pct"] is None


def test_snapshot_fetch_failure_returns_all_none():
    with _mock_fetch({}):
        snap = get_macro_snapshot()

    for entry in snap.values():
        assert entry["last"] is None
        assert entry["change_pct"] is None


def test_snapshot_positive_and_negative_changes():
    with _mock_fetch():
        snap = get_macro_snapshot()

    # S&P went up
    assert snap["sp500"]["change_pct"] > 0
    # Nasdaq went slightly down
    assert snap["nasdaq"]["change_pct"] < 0


# ── get_macro_summary_text tests ──────────────────────────────────────────────

def test_summary_text_contains_header():
    with _mock_fetch():
        text = get_macro_summary_text()

    assert "Macro Snapshot" in text


def test_summary_text_contains_section_headers():
    with _mock_fetch():
        text = get_macro_summary_text()

    assert "[World]" in text
    assert "[Indonesia]" in text


def test_summary_text_contains_key_labels():
    with _mock_fetch():
        text = get_macro_summary_text()

    for label in ("S&P 500", "Nasdaq", "VIX", "Gold", "IDX Composite", "USD/IDR"):
        assert label in text, f"Missing label: {label}"


def test_summary_text_shows_na_for_missing():
    with _mock_fetch({}):
        text = get_macro_summary_text()

    assert "N/A" in text


def test_summary_text_accepts_precomputed_snapshot():
    snap = {k: {"last": None, "change_pct": None} for k in [
        "sp500", "nasdaq", "dow", "vix",
        "oil_wti", "gold", "us_10y_yield", "dxy",
        "idx_composite", "usd_idr",
    ]}
    # Should not call _fetch_quotes at all when snapshot is pre-supplied
    with patch("src.macro.snapshot._fetch_quotes") as mock_fetch:
        text = get_macro_summary_text(snap)
        mock_fetch.assert_not_called()

    assert "Macro Snapshot" in text


def test_summary_text_sign_prefix():
    with _mock_fetch():
        text = get_macro_summary_text()

    # S&P is up → should have a '+' sign
    assert "+" in text
