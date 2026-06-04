"""
Morning brief delivery.

compose_morning_messages(bundle) — formats the bundle into 1–2 WhatsApp messages.
send_morning_brief(bundle=None)  — builds (or accepts) a bundle, formats, and sends.

Macro/news NARRATIVE is intentionally absent; that part is written by the scheduled
Claude routine that consumes the JSON produced by build_morning_bundle(). This module
formats structured facts only.

CLI:
    python -m src.report.send_brief [--dry-run] [--date YYYY-MM-DD] [--holdings PATH]
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from src.config import get_settings
from src.notifications import get_notifier
from src.report.build_brief import (
    _HOLDINGS_CSV,
    _IDX_WATCHLIST,
    _REPORTS_DIR,
    _US_WATCHLIST,
    build_morning_bundle,
)

# ── Constants ─────────────────────────────────────────────────────────────────

WHATSAPP_LIMIT = 4096  # characters per message

_DISCLAIMER = (
    "⚠️ _Research & decision-support only. Not financial advice. "
    "No trades are executed by this system._"
)

_MAX_PORTFOLIO_MOVERS = 5   # top movers shown in portfolio section
_MAX_SIGNALS_DEFAULT  = 10  # max signals before we start truncating
_MAX_SIGNALS_COMPACT  = 4   # signals per type when length-trimming


# ── Price / change formatters ─────────────────────────────────────────────────

def _fmt_price(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    if v >= 1_000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:.2f}"
    return f"{v:.4f}"


def _fmt_chg(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    sign  = "+" if v >= 0 else ""
    arrow = "▲" if v > 0 else "▼" if v < 0 else "─"
    return f"{sign}{v:.2f}% {arrow}"


def _fmt_date(date_str: str) -> str:
    """'2026-06-04'  →  '4 Jun 2026'"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%-d %b %Y")
    except Exception:
        # Windows strftime doesn't support %-d; fall back
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            return f"{d.day} {d.strftime('%b %Y')}"
        except Exception:
            return date_str


# ── Section composers ─────────────────────────────────────────────────────────

def _fmt_macro_section(macro: Optional[dict]) -> str:
    if not macro:
        return "🌍 *World* — data unavailable\n🇮🇩 *Indonesia* — data unavailable"

    def _row(key: str) -> tuple[Optional[float], Optional[float]]:
        e = macro.get(key, {})
        return e.get("last"), e.get("change_pct")

    world_lines = ["🌍 *World*"]
    for label, key in [
        ("S&P 500",   "sp500"),
        ("Nasdaq",    "nasdaq"),
        ("VIX",       "vix"),
        ("Oil WTI",   "oil_wti"),
        ("Gold",      "gold"),
        ("US 10Y",    "us_10y_yield"),
        ("DXY",       "dxy"),
    ]:
        last, chg = _row(key)
        world_lines.append(f"• {label}  {_fmt_price(last)}  {_fmt_chg(chg)}")

    indo_lines = ["🇮🇩 *Indonesia*"]
    for label, key in [
        ("IDX",     "idx_composite"),
        ("USD/IDR", "usd_idr"),
    ]:
        last, chg = _row(key)
        indo_lines.append(f"• {label}  {_fmt_price(last)}  {_fmt_chg(chg)}")

    return "\n".join(world_lines) + "\n\n" + "\n".join(indo_lines)


def _fmt_portfolio_section(pf: Optional[dict]) -> str:
    if not pf:
        return "💼 *Portfolio* — data unavailable"

    mv      = pf.get("total_market_value") or 0.0
    pl      = pf.get("total_unrealized_pl") or 0.0
    pl_pct  = pf.get("total_unrealized_pl_pct") or 0.0
    dc      = pf.get("total_day_change")
    idr     = pf.get("total_value_idr")

    pl_sign = "+" if pl >= 0 else ""
    dc_str  = f"{'+' if (dc or 0) >= 0 else ''}{_fmt_price(dc)}" if dc is not None else "N/A"
    idr_str = f"\nIDR Total: {idr:,.0f}" if idr is not None else ""

    lines = [
        "💼 *Portfolio*",
        f"Value: {_fmt_price(mv)}  |  P/L: {pl_sign}{_fmt_price(pl)} ({pl_sign}{pl_pct:.2f}%)",
        f"Day change: {dc_str}{idr_str}",
    ]

    # Top movers sorted by |day_change_pct| descending
    positions = [p for p in (pf.get("positions") or []) if p.get("day_change_pct") is not None]
    positions.sort(key=lambda p: abs(p["day_change_pct"]), reverse=True)
    movers = positions[:_MAX_PORTFOLIO_MOVERS]

    if movers:
        lines.append("")
        lines.append("*Top movers:*")
        for p in movers:
            lines.append(
                f"• {p['ticker']} ({p['market']})  "
                f"{_fmt_price(p.get('last_price'))}  "
                f"{_fmt_chg(p.get('day_change_pct'))}"
            )

    return "\n".join(lines)


def _fmt_one_signal(s: dict) -> list[str]:
    """Format a single signal dict into display lines."""
    ticker = s.get("ticker", "?")
    market = s.get("market", "")
    conf   = s.get("confidence", 0)
    ind    = s.get("indicators", {})
    close  = ind.get("close")
    rc     = s.get("risk_control")

    lines = [f"• *{ticker}* ({market})  {_fmt_price(close)}  Conf: {conf}%"]

    if rc:
        lines.append(
            f"  Entry {_fmt_price(rc['entry_low'])}–{_fmt_price(rc['entry_high'])}  "
            f"Stop {_fmt_price(rc['stop_loss'])}  "
            f"Tgt {_fmt_price(rc['target'])}  "
            f"R/R {rc['risk_reward']:.1f}×"
        )

    reasons = s.get("reasons", [])
    if reasons:
        lines.append(f"  ↳ {reasons[0]}")

    inv = s.get("invalidation_conditions", [])
    if inv:
        lines.append(f"  ✗ {inv[0]}")

    return lines


def _fmt_signals_section(
    signals: dict,
    max_per_type: int = _MAX_SIGNALS_DEFAULT,
) -> str:
    all_signals = (signals.get("portfolio") or []) + (signals.get("watchlist") or [])

    buys  = [s for s in all_signals if s.get("signal_type") == "BUY_WATCHLIST"]
    sells = [s for s in all_signals if s.get("signal_type") == "SELL_WARNING"]

    # Sort each group by confidence desc
    buys.sort(key=lambda s: s.get("confidence", 0), reverse=True)
    sells.sort(key=lambda s: s.get("confidence", 0), reverse=True)

    buys  = buys[:max_per_type]
    sells = sells[:max_per_type]

    parts: list[str] = []

    if buys:
        lines = [f"📈 *Buy Watchlist* ({len(buys)})"]
        for s in buys:
            lines.extend(_fmt_one_signal(s))
        parts.append("\n".join(lines))

    if sells:
        lines = [f"📉 *Sell Warnings* ({len(sells)})"]
        for s in sells:
            lines.extend(_fmt_one_signal(s))
        parts.append("\n".join(lines))

    if not buys and not sells:
        parts.append("🔍 *Signals* — no actionable signals today")

    return "\n\n".join(parts)


# ── Message assembly ──────────────────────────────────────────────────────────

def compose_morning_messages(bundle: dict) -> list[str]:
    """
    Compose 1–2 WhatsApp messages from a morning bundle dict.

    Fitting strategy:
      1. Single message if ≤ WHATSAPP_LIMIT chars.
      2. Two messages (macro+portfolio | signals+footer) if each fits.
      3. Truncate signals to _MAX_SIGNALS_COMPACT per type if msg2 still too long.

    Always returns at least one non-empty string.
    """
    date_str = bundle.get("date", "")
    header   = f"📊 *Morning Brief* — {_fmt_date(date_str)}"

    macro_text = _fmt_macro_section(bundle.get("macro"))
    pf_text    = _fmt_portfolio_section(bundle.get("portfolio"))
    sigs_text  = _fmt_signals_section(bundle.get("signals", {}))

    part1 = "\n\n".join([header, macro_text, pf_text])
    part2 = "\n\n".join([sigs_text, _DISCLAIMER])

    full = part1 + "\n\n" + part2
    if len(full) <= WHATSAPP_LIMIT:
        return [full]

    # Try two-part split
    if len(part2) > WHATSAPP_LIMIT:
        sigs_text  = _fmt_signals_section(bundle.get("signals", {}), max_per_type=_MAX_SIGNALS_COMPACT)
        sigs_text += f"\n\n_Showing top {_MAX_SIGNALS_COMPACT} signals. Full brief saved to reports/._"
        part2 = "\n\n".join([sigs_text, _DISCLAIMER])

    return [part1, part2]


# ── File save ─────────────────────────────────────────────────────────────────

def _save_full_text(messages: list[str], date_str: str, out_dir: Path) -> Path:
    """Save the composed message(s) to a text file for auditing."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"morning_whatsapp_{date_str}.txt"
    path.write_text("\n\n---\n\n".join(messages), encoding="utf-8")
    logger.info(f"[send_brief] Full text saved → {path}")
    return path


# ── Main delivery function ────────────────────────────────────────────────────

def send_morning_brief(
    bundle: Optional[dict] = None,
    settings=None,
    recipient: Optional[str] = None,
    run_date: Optional[date] = None,
    holdings_path: Path = _HOLDINGS_CSV,
    idx_watchlist_path: Path = _IDX_WATCHLIST,
    us_watchlist_path: Path = _US_WATCHLIST,
    out_dir: Path = _REPORTS_DIR,
) -> bool:
    """
    Build (or accept a pre-built) morning bundle, compose WhatsApp messages,
    and send via the configured notifier.

    Args:
        bundle:    Pre-built bundle dict. If None, build_morning_bundle() is called.
        settings:  Settings instance. If None, loaded from environment.
        recipient: Override recipient phone number.
        run_date:  Date to pass to build_morning_bundle when building fresh.
        holdings_path / idx_watchlist_path / us_watchlist_path:
                   Passed through to build_morning_bundle when building fresh.
        out_dir:   Directory for the saved text file.

    Returns True if all messages were sent successfully (or dry-run).
    """
    if settings is None:
        settings = get_settings()

    if bundle is None:
        logger.info("[send_brief] Building morning bundle...")
        bundle = build_morning_bundle(
            run_date=run_date,
            holdings_path=holdings_path,
            idx_watchlist_path=idx_watchlist_path,
            us_watchlist_path=us_watchlist_path,
            out_dir=out_dir,
        )

    date_str = bundle.get("date", "unknown")

    logger.info("[send_brief] Composing WhatsApp message(s)...")
    messages = compose_morning_messages(bundle)

    # Always persist the full composed text
    _save_full_text(messages, date_str, out_dir)

    if settings.dry_run:
        sep = "=" * 60
        for i, msg in enumerate(messages, 1):
            print(f"\n{sep}\n[DRY RUN] Message {i}/{len(messages)}\n{sep}\n{msg}\n{sep}")
        logger.info(f"[send_brief] DRY_RUN — {len(messages)} message(s) previewed, not sent")
        return True

    notifier = get_notifier(settings)
    all_ok = True
    for i, msg in enumerate(messages, 1):
        logger.info(f"[send_brief] Sending message {i}/{len(messages)} ({len(msg)} chars)...")
        ok = notifier.send(msg, recipient=recipient)
        if not ok:
            logger.error(f"[send_brief] Message {i} failed to send")
            all_ok = False

    return all_ok


# ── CLI ───────────────────────────────────────────────────────────────────────

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Compose and send the morning market brief via WhatsApp.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Preview message(s) without sending. Overrides DRY_RUN env var.",
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
        help="Output directory for saved text and JSON.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if args.dry_run:
        # CLI --dry-run overrides the env setting for this run
        settings = settings.model_copy(update={"dry_run": True})

    logger.info("[send_brief] Starting morning brief delivery...")
    ok = send_morning_brief(
        settings=settings,
        run_date=args.date,
        holdings_path=args.holdings,
        out_dir=args.out_dir,
    )

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    _main()
