"""
Macro narrative generation via Claude with server-side web_search.

generate_macro_narrative(bundle) -> str

Calls claude-sonnet-4-6 (max_tokens=1500) with the web_search_20250305
built-in tool so Claude can corroborate the bundle data with live news.

Falls back to a plain-text summary built from bundle raw numbers if
ANTHROPIC_API_KEY is missing or the API call fails — so the morning brief
always has a lead section even without a key.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from loguru import logger


_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1500

_SYSTEM_PROMPT = (
    "You are a private market analyst preparing a morning brief for a retail investor "
    "based in Jakarta. Base analysis ONLY on the data provided plus your web research. "
    "Never fabricate numbers. This is decision-support only, not financial advice."
)

_USER_SUFFIX = (
    "\n\nKeep your response under 800 words. No markdown tables — use plain bullet points only. "
    "Avoid entry/stop/target price tables; those are handled separately by the signal engine.\n\n"
    "Structure your response as:\n"
    "(1) What happened overnight in world markets and why (2-3 sentences).\n"
    "(2) What this means for IDX and the rupiah today (2-3 sentences).\n"
    "(3) One key risk to watch (1-2 sentences).\n"
    "Then list any BUY_WATCHLIST signals from the bundle as plain bullet points "
    "with a one-line rationale each (no prices, no tables). "
    "Be direct and concise."
)


def generate_macro_narrative(bundle: dict) -> str:
    """
    Return a concise AI-written morning narrative for the WhatsApp brief.

    Tries Claude claude-sonnet-4-6 with web_search enabled; falls back to a
    plain-text rule-based summary if the API key is absent or the call fails.
    """
    api_key = _resolve_api_key()

    if api_key:
        try:
            return _call_claude(bundle, api_key)
        except Exception as exc:
            logger.warning(f"[macro_narrative] Claude API failed ({exc}). Using rule-based fallback.")
    else:
        logger.warning("[macro_narrative] ANTHROPIC_API_KEY not set. Using rule-based fallback.")

    return _fallback_summary(bundle)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _resolve_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        from src.config import get_settings
        return get_settings().anthropic_api_key or ""
    except Exception:
        return ""


def _call_claude(bundle: dict, api_key: str) -> str:
    import anthropic  # lazy import so missing package is a soft failure

    bundle_text = json.dumps(bundle, indent=2, ensure_ascii=False)
    user_message = bundle_text + _USER_SUFFIX

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": user_message}],
    )

    # Server-side web_search blocks are handled by Anthropic; we collect text.
    text_parts = [block.text for block in response.content if hasattr(block, "text")]
    return "\n".join(text_parts).strip()


def _fallback_summary(bundle: dict) -> str:
    """Build a plain-text narrative from raw bundle numbers — no LLM."""
    lines: list[str] = ["📋 *Market Narrative* (rule-based — AI unavailable)"]

    macro = bundle.get("macro") or {}

    def _row(key: str):
        e = macro.get(key) or {}
        return e.get("last"), e.get("change_pct")

    def _sign(v: Optional[float]) -> str:
        if v is None:
            return "N/A"
        return f"{'+' if v >= 0 else ''}{v:.2f}%"

    sp_last,  sp_chg  = _row("sp500")
    nq_last,  nq_chg  = _row("nasdaq")
    vix_last, _       = _row("vix")
    oil_last, oil_chg = _row("oil_wti")
    dxy_last, dxy_chg = _row("dxy")
    idx_last, idx_chg = _row("idx_composite")
    idr_last, idr_chg = _row("usd_idr")

    # Overnight world
    overnight: list[str] = []
    if sp_last is not None:
        mv = "rose" if (sp_chg or 0) >= 0 else "fell"
        overnight.append(f"S&P 500 {mv} {_sign(sp_chg)} to {sp_last:,.2f}")
    if nq_last is not None:
        mv = "rose" if (nq_chg or 0) >= 0 else "fell"
        overnight.append(f"Nasdaq {mv} {_sign(nq_chg)}")
    if oil_last is not None:
        overnight.append(f"Oil WTI {oil_last:.2f} ({_sign(oil_chg)})")
    if vix_last is not None:
        risk = "elevated — caution" if vix_last > 20 else "contained"
        overnight.append(f"VIX {vix_last:.2f} ({risk})")
    if dxy_last is not None:
        overnight.append(f"DXY {dxy_last:.2f} ({_sign(dxy_chg)})")
    if overnight:
        lines.append("Overnight: " + "; ".join(overnight) + ".")

    # IDX / rupiah impact
    indo: list[str] = []
    if idx_last is not None:
        indo.append(f"IDX composite {idx_last:,.2f} ({_sign(idx_chg)})")
    if idr_last is not None:
        indo.append(f"USD/IDR {idr_last:,.0f} ({_sign(idr_chg)})")
    if indo:
        lines.append("Indonesia: " + "; ".join(indo) + ".")

    # Risk flag
    if vix_last is not None and vix_last > 25:
        lines.append("⚠️ Key risk: VIX above 25 signals elevated equity volatility — reduce position sizing.")
    elif dxy_last is not None and (dxy_chg or 0) > 0.5:
        lines.append("⚠️ Key risk: Strengthening USD adds pressure on the rupiah and commodity imports.")
    else:
        lines.append("Key risk: Monitor US macro data releases and Fed commentary for direction shifts.")

    # BUY_WATCHLIST signals from the bundle
    all_sigs = (
        (bundle.get("signals") or {}).get("portfolio", []) +
        (bundle.get("signals") or {}).get("watchlist", [])
    )
    buys = [s for s in all_sigs if s.get("signal_type") == "BUY_WATCHLIST"]

    if buys:
        lines.append("\n📈 *Buy Watchlist Signals:*")
        for s in buys:
            reasons   = s.get("reasons") or []
            rationale = reasons[0] if reasons else "Technical setup triggered"
            ticker    = s.get("ticker", "?")
            market    = s.get("market", "")
            conf      = s.get("confidence", 0)
            lines.append(f"• {ticker} ({market}, conf {conf}%): {rationale}")
    else:
        lines.append("\nNo BUY_WATCHLIST signals in today's scan.")

    return "\n".join(lines)
