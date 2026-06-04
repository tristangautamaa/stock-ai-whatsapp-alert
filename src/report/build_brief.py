"""
Morning bundle builder.

build_morning_bundle() assembles macro snapshot, portfolio valuation, and
signal scans into a single JSON the report routine will consume, plus a
plain-text markdown brief (no LLM — structured facts only).

CLI:
    python -m src.report.build_brief [--date YYYY-MM-DD] [--holdings PATH] [--out-dir PATH]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from loguru import logger


# ── Project-relative defaults ─────────────────────────────────────────────────

_PROJECT_ROOT   = Path(__file__).parent.parent.parent
_REPORTS_DIR    = _PROJECT_ROOT / "reports"
_HOLDINGS_CSV   = _PROJECT_ROOT / "portfolio" / "holdings.csv"
_IDX_WATCHLIST  = _PROJECT_ROOT / "watchlists" / "idx_sample.csv"
_US_WATCHLIST   = _PROJECT_ROOT / "watchlists" / "us_sample.csv"


# ── JSON serialization ─────────────────────────────────────────────────────────

class _Encoder(json.JSONEncoder):
    """Handle datetime, Enum, and dataclass instances that survive into the bundle."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        return super().default(obj)


# ── Watchlist loader ──────────────────────────────────────────────────────────

def _load_watchlist(path: Path) -> list[str]:
    """Read tickers from a newline-separated file; skip blanks and # comments."""
    if not path.exists():
        logger.warning(f"[build_brief] Watchlist not found: {path}")
        return []
    tickers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t and not t.startswith("#"):
            tickers.append(t.upper())
    return tickers


# ── Signal scanner ────────────────────────────────────────────────────────────

def _scan_tickers(
    pairs: list[tuple[str, str]],
) -> tuple[list[dict], list[str]]:
    """
    Fetch OHLCV, compute indicators, and generate a signal for each
    (ticker, market) pair. Returns (actionable_signals, per_ticker_errors).
    Only BUY_WATCHLIST and SELL_WARNING signals are included in results.
    """
    from src.data.yfinance_provider import YFinanceProvider
    from src.indicators.technicals import compute_indicators
    from src.signals.engine import generate_signal

    provider = YFinanceProvider()
    results: list[dict] = []
    errors: list[str] = []

    for ticker, market in pairs:
        try:
            df = provider.get_ohlcv(ticker, period="6mo", interval="1d")
            if df.empty:
                errors.append(f"{ticker}: no OHLCV data returned")
                continue
            indicators = compute_indicators(df)
            if not indicators:
                errors.append(f"{ticker}: insufficient data for indicators (need ≥50 rows)")
                continue
            signal = generate_signal(ticker, indicators, market=market)
            if signal.is_actionable:
                results.append(signal.model_dump(mode="json"))
        except Exception as exc:
            errors.append(f"{ticker}: {exc}")
            logger.error(f"[build_brief] {ticker} scan failed: {exc}")

    return results, errors


# ── Section builders ──────────────────────────────────────────────────────────

def _build_macro() -> tuple[dict | None, str | None]:
    """Fetch macro snapshot. Returns (snapshot_dict, error_str)."""
    try:
        from src.macro.snapshot import get_macro_snapshot
        return get_macro_snapshot(), None
    except Exception as exc:
        logger.error(f"[build_brief] Macro snapshot failed: {exc}")
        return None, str(exc)


def _build_portfolio(holdings_path: Path) -> tuple[dict | None, str | None]:
    """Load and value the portfolio. Returns (portfolio_dict, error_str)."""
    try:
        from src.portfolio.portfolio import load_holdings, value_portfolio
        holdings = load_holdings(holdings_path)
        if not holdings:
            return {
                "positions": [],
                "total_cost_basis": 0.0,
                "total_market_value": 0.0,
                "total_unrealized_pl": 0.0,
                "total_unrealized_pl_pct": 0.0,
                "total_day_change": None,
                "usd_idr_rate": None,
                "total_value_idr": None,
            }, None
        summary = value_portfolio(holdings)
        return dataclasses.asdict(summary), None
    except Exception as exc:
        logger.error(f"[build_brief] Portfolio valuation failed: {exc}")
        return None, str(exc)


def _build_signals(
    holdings_path: Path,
    idx_watchlist_path: Path,
    us_watchlist_path: Path,
) -> tuple[dict[str, list[dict]], dict[str, list[str]]]:
    """
    Run signal scans for portfolio tickers and watchlist tickers.
    Returns (signals_dict, errors_dict); signals always has 'portfolio' and
    'watchlist' keys even when empty.
    """
    signals: dict[str, list[dict]] = {"portfolio": [], "watchlist": []}
    errors:  dict[str, list[str]]  = {}

    # Portfolio tickers
    try:
        from src.portfolio.portfolio import load_holdings
        holdings = load_holdings(holdings_path)
        pairs = [(h.ticker, h.market) for h in holdings]
        results, errs = _scan_tickers(pairs)
        signals["portfolio"] = results
        if errs:
            errors["portfolio"] = errs
    except Exception as exc:
        logger.error(f"[build_brief] Portfolio signal scan failed: {exc}")
        errors["portfolio"] = [str(exc)]

    # Watchlist tickers
    idx_tickers = _load_watchlist(idx_watchlist_path)
    us_tickers  = _load_watchlist(us_watchlist_path)
    watchlist_pairs = (
        [(t, "IDX") for t in idx_tickers] +
        [(t, "US")  for t in us_tickers]
    )
    try:
        results, errs = _scan_tickers(watchlist_pairs)
        signals["watchlist"] = results
        if errs:
            errors["watchlist"] = errs
    except Exception as exc:
        logger.error(f"[build_brief] Watchlist signal scan failed: {exc}")
        errors["watchlist"] = [str(exc)]

    return signals, errors


# ── Markdown brief renderer ───────────────────────────────────────────────────

def _render_brief(bundle: dict) -> str:
    """Render the bundle as a human-readable markdown brief (no LLM)."""
    run_date     = bundle.get("date", "")
    generated_at = bundle.get("generated_at", "")
    lines: list[str] = [f"# Morning Brief — {run_date}", ""]

    # Macro
    lines += ["## Macro Snapshot", ""]
    macro = bundle.get("macro")
    if macro:
        from src.macro.snapshot import get_macro_summary_text
        lines.append(get_macro_summary_text(macro))
    else:
        lines.append("*Macro data unavailable.*")
    lines.append("")

    # Portfolio
    lines += ["## Portfolio", ""]
    pf = bundle.get("portfolio")
    if pf:
        mv      = pf.get("total_market_value") or 0.0
        pl      = pf.get("total_unrealized_pl") or 0.0
        pl_pct  = pf.get("total_unrealized_pl_pct") or 0.0
        dc      = pf.get("total_day_change")
        idr     = pf.get("total_value_idr")

        dc_str  = f"{dc:+,.2f}" if dc is not None else "N/A"
        idr_str = f"  |  IDR Total: {idr:,.0f}" if idr is not None else ""
        lines.append(
            f"**Market Value:** {mv:,.2f}  |  "
            f"**Unrealized P/L:** {pl:+,.2f} ({pl_pct:+.2f}%)  |  "
            f"**Day Change:** {dc_str}"
            f"{idr_str}"
        )
        lines.append("")

        positions = pf.get("positions", [])
        if positions:
            lines.append("| Ticker   | Mkt | Last Price |  Mkt Value | Unrealized P/L         | Day Chg   | Weight |")
            lines.append("|----------|-----|-----------|-----------|------------------------|-----------|--------|")
            for p in positions:
                lp   = f"{p['last_price']:>11,.2f}"     if p.get("last_price")    is not None else "        N/A"
                mv2  = f"{p['market_value']:>11,.2f}"   if p.get("market_value")  is not None else "        N/A"
                upl_v = p.get("unrealized_pl")
                upl_p = p.get("unrealized_pl_pct")
                upl  = f"{upl_v:+,.2f} ({upl_p:+.2f}%)" if upl_v is not None else "N/A"
                dc2  = f"{p['day_change']:+,.2f}"        if p.get("day_change")   is not None else "N/A"
                wt   = f"{p['weight_pct']:.1f}%"        if p.get("weight_pct")   is not None else "N/A"
                lines.append(f"| {p['ticker']:<8} | {p['market']:<3} | {lp} | {mv2} | {upl:<22} | {dc2:>9} | {wt:>6} |")
    else:
        lines.append("*Portfolio data unavailable.*")
    lines.append("")

    # Signals
    lines += ["## Actionable Signals", ""]
    sigs = bundle.get("signals", {})

    def _fmt_section(signal_list: list[dict], title: str) -> list[str]:
        out = [f"### {title}", ""]
        if not signal_list:
            out += ["*No actionable signals.*", ""]
            return out
        for s in signal_list:
            tkr  = s.get("ticker", "")
            mrkt = s.get("market", "")
            st   = s.get("signal_type", "")
            conf = s.get("confidence", 0)
            out.append(f"**{tkr}** ({mrkt}) — `{st}` | Confidence: {conf}%")
            for r in s.get("reasons", []):
                out.append(f"  - {r}")
            rc = s.get("risk_control")
            if rc:
                out.append(
                    f"  - Entry: {rc['entry_low']:,.2f}–{rc['entry_high']:,.2f}  "
                    f"Stop: {rc['stop_loss']:,.2f}  "
                    f"Target: {rc['target']:,.2f}  "
                    f"R/R: {rc['risk_reward']:.1f}"
                )
            inv = s.get("invalidation_conditions", [])
            if inv:
                out.append(f"  - Invalidation: {'; '.join(inv)}")
            out.append("")
        return out

    lines += _fmt_section(sigs.get("portfolio", []), "Portfolio Signals")
    lines += _fmt_section(sigs.get("watchlist", []), "Watchlist Signals")

    # Errors
    errors = bundle.get("errors", {})
    err_lines: list[str] = []
    for section, val in errors.items():
        if isinstance(val, str):
            err_lines.append(f"- **{section}**: {val}")
        elif isinstance(val, list):
            for e in val:
                err_lines.append(f"- **{section}**: {e}")
        elif isinstance(val, dict):
            for sub, sub_errs in val.items():
                for e in (sub_errs or []):
                    err_lines.append(f"- **{section}/{sub}**: {e}")

    if err_lines:
        lines += ["## Errors", ""]
        lines += err_lines
        lines.append("")

    lines.append(f"---\n*Generated at {generated_at}. No LLM — structured facts only.*")
    return "\n".join(lines)


# ── Orchestrator ──────────────────────────────────────────────────────────────

def build_morning_bundle(
    run_date: date | None = None,
    holdings_path: Path = _HOLDINGS_CSV,
    idx_watchlist_path: Path = _IDX_WATCHLIST,
    us_watchlist_path: Path = _US_WATCHLIST,
    out_dir: Path = _REPORTS_DIR,
) -> dict:
    """
    Assemble macro snapshot, portfolio valuation, and signal scans into one bundle.

    Each section is isolated: a failure in one does not block the others. Failed
    sections appear in the 'errors' key of the returned dict and the written JSON.

    Writes:
        <out_dir>/morning_data_<date>.json  — machine-readable bundle
        <out_dir>/morning_brief_<date>.md   — plain-text brief (no LLM)

    Returns the full bundle dict.
    """
    if run_date is None:
        run_date = date.today()

    date_str     = run_date.strftime("%Y-%m-%d")
    generated_at = datetime.now(tz=timezone.utc).isoformat()

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"morning_data_{date_str}.json"
    md_path   = out_dir / f"morning_brief_{date_str}.md"

    errors: dict[str, Any] = {}

    logger.info("[build_brief] Fetching macro snapshot...")
    macro, macro_err = _build_macro()
    if macro_err:
        errors["macro"] = macro_err

    logger.info("[build_brief] Valuing portfolio...")
    portfolio, pf_err = _build_portfolio(holdings_path)
    if pf_err:
        errors["portfolio"] = pf_err

    logger.info("[build_brief] Running signal scans...")
    signals, sig_errors = _build_signals(holdings_path, idx_watchlist_path, us_watchlist_path)
    if sig_errors:
        errors["signals"] = sig_errors

    bundle: dict[str, Any] = {
        "date":         date_str,
        "generated_at": generated_at,
        "macro":        macro,
        "portfolio":    portfolio,
        "signals":      signals,
        "errors":       errors,
    }

    json_path.write_text(
        json.dumps(bundle, indent=2, cls=_Encoder, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"[build_brief] JSON written → {json_path}")

    brief_text = _render_brief(bundle)
    md_path.write_text(brief_text, encoding="utf-8")
    logger.info(f"[build_brief] Brief written → {md_path}")

    return bundle


# ── CLI ───────────────────────────────────────────────────────────────────────

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Build morning data bundle and plain-text brief.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="Override run date. Defaults to today.",
    )
    parser.add_argument(
        "--holdings",
        type=Path,
        default=_HOLDINGS_CSV,
        help="Path to holdings CSV.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_REPORTS_DIR,
        help="Output directory for JSON and MD files.",
    )
    args = parser.parse_args()

    logger.info("[build_brief] Starting morning bundle build...")
    bundle = build_morning_bundle(
        run_date=args.date,
        holdings_path=args.holdings,
        out_dir=args.out_dir,
    )

    n_pf  = len(bundle.get("signals", {}).get("portfolio", []))
    n_wl  = len(bundle.get("signals", {}).get("watchlist", []))
    errs  = bundle.get("errors", {})
    n_err = sum(
        1 if isinstance(v, str) else len(v) if isinstance(v, list)
        else sum(len(sub) for sub in v.values()) if isinstance(v, dict) else 0
        for v in errs.values()
    )

    date_str = bundle["date"]
    out_dir  = args.out_dir
    print(f"\nBundle complete — {date_str}")
    print(f"  Portfolio signals: {n_pf} actionable")
    print(f"  Watchlist signals: {n_wl} actionable")
    if n_err:
        print(f"  Errors:           {n_err} (see 'errors' in JSON)")
    print(f"\n  JSON  → {out_dir / f'morning_data_{date_str}.json'}")
    print(f"  Brief → {out_dir / f'morning_brief_{date_str}.md'}")


if __name__ == "__main__":
    _main()
