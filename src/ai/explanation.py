from loguru import logger
from ..signals.schemas import Signal
from ..config import Settings


def generate_explanation(signal: Signal, settings: Settings) -> str:
    """
    Generate a natural-language explanation grounded in computed indicators.
    Tries Anthropic first, then OpenAI, then falls back to rule-based text.
    Never fabricates market data or makes profit promises.
    """
    if settings.has_anthropic:
        return _explain_anthropic(signal, settings)
    if settings.has_openai:
        return _explain_openai(signal, settings)
    return _explain_rule_based(signal)


def _explain_anthropic(signal: Signal, settings: Settings) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=350,
            messages=[{"role": "user", "content": _build_prompt(signal)}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Anthropic explanation failed: {e}")
        return _explain_rule_based(signal)


def _explain_openai(signal: Signal, settings: Settings) -> str:
    try:
        import openai
        client = openai.OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=350,
            messages=[{"role": "user", "content": _build_prompt(signal)}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"OpenAI explanation failed: {e}")
        return _explain_rule_based(signal)


def _build_prompt(signal: Signal) -> str:
    ind = signal.indicators
    return f"""You are a quantitative analyst assistant for a private stock monitoring tool.

Write a concise 2-3 sentence explanation of why this alert was generated.
- Base your explanation ONLY on the indicator data below.
- Do NOT fabricate any data, prices, or events not listed here.
- Do NOT promise any profit or guarantee any outcome.
- End with one short risk caveat sentence.

Stock: {signal.ticker}
Signal: {signal.signal_type.value}
Confidence: {signal.confidence}/100
Close: {ind.get('close', 'N/A')}
RSI: {ind.get('rsi', 'N/A')}
MA20 distance: {ind.get('ma20_distance_pct', 'N/A')}%
Volume ratio vs 20d avg: {ind.get('volume_ratio', 'N/A')}x
MACD histogram: {ind.get('macd_hist', 'N/A')}
Market regime: {ind.get('regime', 'N/A')}
Key reasons: {'; '.join(signal.reasons[:3])}"""


def _explain_rule_based(signal: Signal) -> str:
    reasons = "; ".join(signal.reasons[:3]) if signal.reasons else "See indicator data"
    return (
        f"Signal generated based on: {reasons}. "
        f"Rule-based confidence: {signal.confidence}/100. "
        f"This is automated analysis — manual review required before any decision."
    )
