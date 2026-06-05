"""
Rich HTML email generator for the morning brief.

generate_html_report(bundle, narrative, signals) → str (full HTML document)

Uses inline CSS only — no external stylesheets (Gmail strips them).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

# ── Palette ───────────────────────────────────────────────────────────────────

RED    = "#e74c3c"
GREEN  = "#27ae60"
DARK   = "#1a1a2e"
ACCENT = "#f39c12"
GREY   = "#7f8c8d"
LGREY  = "#ecf0f1"
WHITE  = "#ffffff"
BORDER = "#dde1e7"
TEXT   = "#2c3e50"
MUTED  = "#95a5a6"


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _color(v: Optional[float]) -> str:
    if v is None or v == 0:
        return GREY
    return GREEN if v > 0 else RED


def _td(content: str, extra: str = "") -> str:
    base = f"padding:9px 14px;border-bottom:1px solid {BORDER};font-size:13px;color:{TEXT};"
    return f"<td style='{base}{extra}'>{content}</td>"


def _th(content: str, bg: str = DARK) -> str:
    base = (
        f"padding:10px 14px;text-align:left;font-size:12px;"
        f"font-weight:600;letter-spacing:0.4px;color:{WHITE};background:{bg};"
    )
    return f"<th style='{base}'>{content}</th>"


def _card(title: str, body: str, header_bg: str = DARK, left_accent: str = "") -> str:
    border_left = f"border-left:4px solid {left_accent};" if left_accent else ""
    return f"""
<div style="background:{WHITE};border-radius:10px;margin-bottom:24px;
            overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);{border_left}">
  <div style="background:{header_bg};padding:13px 20px;">
    <h2 style="margin:0;font-size:15px;font-weight:700;color:{WHITE};
               letter-spacing:0.3px;">{title}</h2>
  </div>
  <div style="padding:20px;">{body}</div>
</div>"""


def _fmt_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.day} {d.strftime('%B %Y')}"
    except Exception:
        return date_str


def _md_to_html(text: str) -> str:
    """Convert the AI narrative (light markdown) to safe inline HTML."""
    # Escape ampersands not already escaped
    text = re.sub(r"&(?!amp;|lt;|gt;|quot;)", "&amp;", text)

    # Horizontal rules
    text = re.sub(r"^\s*---+\s*$", "<hr style='border:none;border-top:1px solid "
                  f"{BORDER};margin:14px 0;'>", text, flags=re.MULTILINE)

    # Bold before italic so **x** doesn't partially match *x*
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         text)

    # Bullet lists — consecutive "- " lines become <ul>
    def _listblock(m: re.Match) -> str:
        items = re.sub(r"^- ", "<li style='margin:3px 0;'>", m.group(), flags=re.MULTILINE)
        items = items.replace("\n", "</li>\n")
        return (f"<ul style='margin:8px 0 8px 18px;padding:0;list-style:disc;"
                f"color:{TEXT};font-size:13px;'>" + items + "</li></ul>")

    text = re.sub(r"((?:^- .+\n?)+)", _listblock, text, flags=re.MULTILINE)

    # Paragraph breaks (two+ blank lines → </p><p>)
    text = re.sub(r"\n{2,}", "</p><p style='margin:10px 0;'>", text)
    text = "<p style='margin:10px 0;'>" + text + "</p>"

    # Single newlines → <br>
    text = text.replace("\n", "<br>")

    return text


# ── Section builders ──────────────────────────────────────────────────────────

def _portfolio_summary(pf: Optional[dict]) -> str:
    if not pf:
        return f"<p style='color:{MUTED};'>Portfolio data unavailable.</p>"

    mv     = pf.get("total_market_value") or 0.0
    pl     = pf.get("total_unrealized_pl") or 0.0
    pl_pct = pf.get("total_unrealized_pl_pct") or 0.0
    dc     = pf.get("total_day_change")
    idr    = pf.get("total_value_idr")

    pl_col  = _color(pl)
    dc_col  = _color(dc)
    pl_sign = "+" if pl >= 0 else ""
    dc_str  = (f"{'+' if (dc or 0) >= 0 else ''}{_fmt_price(dc)}") if dc is not None else "N/A"

    idr_row = (
        f"<div style='margin-top:6px;font-size:12px;color:{MUTED};'>"
        f"IDR Total: {idr:,.0f}</div>"
    ) if idr is not None else ""

    cell = (
        "display:inline-block;min-width:180px;padding:16px 24px;"
        f"border-right:1px solid {BORDER};"
    )
    label_s = f"font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:0.6px;"
    val_s   = "font-size:22px;font-weight:700;margin-top:4px;"

    return f"""
<div style="display:flex;flex-wrap:wrap;gap:0;">
  <div style="{cell}">
    <div style="{label_s}">Total Value</div>
    <div style="{val_s}color:{TEXT};">{_fmt_price(mv)}</div>
    {idr_row}
  </div>
  <div style="{cell}">
    <div style="{label_s}">Unrealized P/L</div>
    <div style="{val_s}color:{pl_col};">{pl_sign}{_fmt_price(pl)}<span style="font-size:14px;margin-left:6px;">({pl_sign}{pl_pct:.2f}%)</span></div>
  </div>
  <div style="{cell}border-right:none;">
    <div style="{label_s}">Day Change</div>
    <div style="{val_s}color:{dc_col};">{dc_str}</div>
  </div>
</div>"""


def _macro_table(macro: Optional[dict]) -> str:
    if not macro:
        return f"<p style='color:{MUTED};'>Macro data unavailable.</p>"

    world = [
        ("S&amp;P 500", "sp500"),
        ("Nasdaq",      "nasdaq"),
        ("VIX",         "vix"),
        ("Oil WTI",     "oil_wti"),
        ("Gold",        "gold"),
        ("US 10Y",      "us_10y_yield"),
        ("DXY",         "dxy"),
    ]
    indo = [
        ("IDX Composite", "idx_composite"),
        ("USD/IDR",        "usd_idr"),
    ]

    def _rows(items: list) -> str:
        out = []
        for label, key in items:
            e    = macro.get(key, {})
            last = e.get("last")
            chg  = e.get("change_pct")
            col  = _color(chg)
            out.append(
                f"<tr>"
                f"{_td(f'<span style=font-weight:600;color:{TEXT};>{label}</span>')}"
                f"{_td(_fmt_price(last))}"
                f"{_td(_fmt_chg(chg), f'color:{col};font-weight:700;')}"
                f"</tr>"
            )
        return "".join(out)

    tbl = (
        "width:100%;border-collapse:collapse;font-size:13px;"
    )

    def _block(icon: str, label: str, items: list) -> str:
        return f"""
<td style="width:50%;vertical-align:top;padding-right:20px;">
  <div style="font-size:12px;font-weight:700;color:{MUTED};text-transform:uppercase;
              letter-spacing:0.5px;margin-bottom:10px;">{icon} {label}</div>
  <table style="{tbl}">{_rows(items)}</table>
</td>"""

    return f"""
<table style="width:100%;border-collapse:collapse;">
  <tr>
    {_block("🌍", "World", world)}
    {_block("🇮🇩", "Indonesia", indo)}
  </tr>
</table>"""


def _signal_table(all_signals: list[dict], signal_type: str) -> str:
    is_buy   = signal_type == "BUY_WATCHLIST"
    hdr_col  = GREEN if is_buy else RED
    icon     = "📈" if is_buy else "📉"
    label    = "Buy Watchlist" if is_buy else "Sell Warnings"
    row_bg   = "#f4fff6" if is_buy else "#fff4f4"

    filtered = sorted(
        [s for s in all_signals if s.get("signal_type") == signal_type],
        key=lambda s: s.get("confidence", 0),
        reverse=True,
    )

    if not filtered:
        return _card(
            f"{icon} {label}",
            f"<p style='color:{MUTED};font-size:13px;'>No {label.lower()} signals today.</p>",
            header_bg=hdr_col,
        )

    headers = ["Ticker", "Price", "Conf %", "Entry Zone", "Stop", "Target", "R/R"]
    head_row = "".join(_th(h, hdr_col) for h in headers)

    rows = []
    for s in filtered:
        ticker = s.get("ticker", "?")
        market = s.get("market", "")
        conf   = s.get("confidence", 0)
        close  = (s.get("indicators") or {}).get("close")
        rc     = s.get("risk_control") or {}

        entry  = f"{_fmt_price(rc.get('entry_low'))} – {_fmt_price(rc.get('entry_high'))}" if rc else "N/A"
        stop   = _fmt_price(rc.get("stop_loss"))   if rc else "N/A"
        target = _fmt_price(rc.get("target"))      if rc else "N/A"
        rr_v   = rc.get("risk_reward")
        rr     = f"{rr_v:.1f}×" if rr_v is not None else "N/A"

        conf_col = GREEN if conf >= 80 else ACCENT if conf >= 65 else GREY

        rows.append(
            f"<tr style='background:{row_bg};'>"
            f"{_td(f'<strong>{ticker}</strong> <span style=font-size:11px;color:{MUTED};>({market})</span>')}"
            f"{_td(_fmt_price(close))}"
            f"{_td(f'<span style=color:{conf_col};font-weight:700;>{conf}%</span>')}"
            f"{_td(entry)}"
            f"{_td(stop, f'color:{RED};')}"
            f"{_td(target, f'color:{GREEN};')}"
            f"{_td(rr, 'font-weight:600;')}"
            f"</tr>"
        )

    body = f"""
<div style="overflow-x:auto;">
  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <thead><tr>{head_row}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</div>"""

    return _card(f"{icon} {label} ({len(filtered)})", body, header_bg=hdr_col)


def _holdings_table(pf: Optional[dict]) -> str:
    if not pf:
        return ""
    positions = pf.get("positions") or []
    if not positions:
        return ""

    headers = ["Ticker", "Mkt", "Shares", "Avg Cost", "Last Price", "Mkt Value", "P/L", "P/L %", "Day %"]
    head_row = "".join(_th(h) for h in headers)

    rows = []
    for p in positions:
        ticker  = p.get("ticker", "?")
        market  = p.get("market", "")
        shares  = p.get("shares", 0)
        pl_v    = p.get("unrealized_pl")
        pl_pct  = p.get("unrealized_pl_pct")
        dc_pct  = p.get("day_change_pct")
        pl_col  = _color(pl_v)
        dc_col  = _color(dc_pct)

        pl_str  = f"{pl_v:+,.2f}"   if pl_v   is not None else "N/A"
        plp_str = f"{pl_pct:+.2f}%" if pl_pct  is not None else "N/A"
        dcp_str = f"{dc_pct:+.2f}%" if dc_pct  is not None else "N/A"
        shr_str = f"{shares:,.0f}"

        rows.append(
            "<tr>"
            f"{_td('<strong>' + ticker + '</strong>')}"
            f"{_td(market)}"
            f"{_td(shr_str)}"
            f"{_td(_fmt_price(p.get('avg_cost')))}"
            f"{_td(_fmt_price(p.get('last_price')))}"
            f"{_td(_fmt_price(p.get('market_value')))}"
            f"{_td(pl_str,  f'color:{pl_col};font-weight:600;')}"
            f"{_td(plp_str, f'color:{pl_col};font-weight:600;')}"
            f"{_td(dcp_str, f'color:{dc_col};')}"
            "</tr>"
        )

    body = f"""
<div style="overflow-x:auto;">
  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <thead><tr>{head_row}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</div>"""

    return _card("💼 Portfolio Holdings", body)


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_html_report(bundle: dict, narrative: str, signals: dict) -> str:
    """Return a complete HTML document for the morning brief email."""

    date_str     = bundle.get("date", "")
    generated_at = bundle.get("generated_at", "")
    date_display = _fmt_date(date_str)

    all_signals = (signals.get("portfolio") or []) + (signals.get("watchlist") or [])

    # ── Build sections ──────────────────────────────────────────────────────
    pf_summary   = _portfolio_summary(bundle.get("portfolio"))
    macro_body   = _macro_table(bundle.get("macro"))
    narrative_html = _md_to_html(narrative) if narrative else (
        f"<p style='color:{MUTED};'>No AI narrative generated.</p>"
    )

    buy_block     = _signal_table(all_signals, "BUY_WATCHLIST")
    sell_block    = _signal_table(all_signals, "SELL_WARNING")
    holdings_block = _holdings_table(bundle.get("portfolio"))

    pf_card     = _card("💼 Portfolio Summary", pf_summary)
    macro_card  = _card("🌍 Market Snapshot",   macro_body)

    ai_card = f"""
<div style="background:{WHITE};border-radius:10px;margin-bottom:24px;
            overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);
            border-left:5px solid {ACCENT};">
  <div style="padding:13px 20px;border-bottom:1px solid {BORDER};">
    <h2 style="margin:0;font-size:15px;font-weight:700;color:{DARK};">🤖 AI Analyst</h2>
  </div>
  <div style="padding:20px;font-size:14px;line-height:1.75;color:{TEXT};">
    {narrative_html}
  </div>
</div>"""

    footer = f"""
<div style="text-align:center;padding:20px 0;color:{MUTED};font-size:11px;
            border-top:1px solid {BORDER};margin-top:10px;">
  ⚠️ Research &amp; decision-support only. Not financial advice.
  No trades are executed by this system.<br>
  <span style="margin-top:4px;display:inline-block;">
    Generated {generated_at} &nbsp;·&nbsp; Goldman Stanley Morning Brief
  </span>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Goldman Stanley Morning Brief — {date_display}</title>
</head>
<body style="margin:0;padding:0;background:#f0f2f5;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">

  <!-- ── Header bar ─────────────────────────────────────────── -->
  <div style="background:{DARK};padding:22px 30px;">
    <table style="width:100%;max-width:920px;margin:0 auto;border-collapse:collapse;">
      <tr>
        <td style="vertical-align:middle;">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:2px;
                      color:{ACCENT};margin-bottom:4px;">Proprietary Research</div>
          <div style="font-size:22px;font-weight:800;color:{WHITE};
                      letter-spacing:0.5px;">Goldman Stanley</div>
          <div style="font-size:13px;color:#a0aec0;margin-top:2px;">Morning Brief</div>
        </td>
        <td style="text-align:right;vertical-align:middle;">
          <div style="font-size:20px;font-weight:700;color:{ACCENT};">{date_display}</div>
          <div style="font-size:12px;color:#a0aec0;margin-top:3px;">Pre-Market Analysis</div>
        </td>
      </tr>
    </table>
  </div>

  <!-- ── Content ────────────────────────────────────────────── -->
  <div style="max-width:920px;margin:0 auto;padding:24px 16px;">
    {pf_card}
    {macro_card}
    {ai_card}
    {buy_block}
    {sell_block}
    {holdings_block}
    {footer}
  </div>

</body>
</html>"""
