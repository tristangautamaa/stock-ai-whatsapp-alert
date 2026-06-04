from ..signals.schemas import Signal, SignalType

SIGNAL_EMOJI = {
    SignalType.BUY_WATCHLIST: "📈",
    SignalType.SELL_WARNING: "📉",
    SignalType.HOLD: "⏸",
    SignalType.AVOID: "🚫",
}

DISCLAIMER = (
    "⚠️ AI-assisted alert only. Not financial advice. "
    "Manual confirmation required. Past performance does not guarantee future results."
)


def format_whatsapp_message(signal: Signal) -> str:
    """Format a Signal into a clean WhatsApp-ready text message."""
    emoji = SIGNAL_EMOJI.get(signal.signal_type, "📊")
    rc = signal.risk_control

    lines = [
        f"{emoji} *Stock Alert: {signal.ticker}*",
        f"Signal: *{signal.signal_type.value}*",
        f"Confidence: {signal.confidence}/100",
        f"Market: {signal.market}",
    ]

    if rc:
        lines += [
            "",
            f"Entry Area: {_fmt(rc.entry_low)} – {_fmt(rc.entry_high)}",
            f"Stop Loss:  {_fmt(rc.stop_loss)}",
            f"Target:     {_fmt(rc.target)}",
            f"Risk/Reward: 1:{rc.risk_reward:.1f}",
        ]

    if signal.reasons:
        lines.append("\n*Why:*")
        for r in signal.reasons[:5]:
            lines.append(f"• {r}")

    if signal.invalidation_conditions:
        lines.append("\n*Invalid if:*")
        for c in signal.invalidation_conditions[:3]:
            lines.append(f"• {c}")

    if signal.ai_explanation:
        lines.append(f"\n💡 {signal.ai_explanation}")

    if signal.timegpt_forecast:
        fc = signal.timegpt_forecast
        lines.append(
            f"\n🔮 TimeGPT {fc['horizon_days']}d outlook: "
            f"{fc['direction']} ({fc['expected_change_pct']:+.1f}%)"
        )

    if signal.sentiment_score is not None:
        sentiment_label = (
            "Positive" if signal.sentiment_score > 0.2
            else "Negative" if signal.sentiment_score < -0.2
            else "Neutral"
        )
        lines.append(f"📰 News sentiment: {sentiment_label} ({signal.sentiment_score:+.2f})")

    lines.append(f"\n{DISCLAIMER}")
    return "\n".join(lines)


def _fmt(value: float) -> str:
    """Format price: comma-separated for IDX, 4dp for sub-1 prices."""
    if value >= 1000:
        return f"{value:,.0f}"
    if value >= 1:
        return f"{value:.2f}"
    return f"{value:.6f}"
