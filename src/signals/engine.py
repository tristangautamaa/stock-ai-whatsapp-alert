from loguru import logger
from .schemas import Signal, SignalType
from .risk import compute_risk_control

# ── Tunable thresholds ────────────────────────────────────────────────────────
RSI_BUY_LOW = 45
RSI_BUY_HIGH = 70
RSI_SELL_MAX = 45
MIN_VOLUME_RATIO = 1.2
MAX_MA20_DIST_PCT = 8.0   # avoid chasing extended moves
MIN_RISK_REWARD = 1.5
EXTREME_VOLATILITY = 100  # annualized %


def generate_signal(ticker: str, indicators: dict, market: str = "IDX") -> Signal:
    """
    Rule-based signal generator.

    Scores BUY_WATCHLIST and SELL_WARNING conditions independently.
    Returns the stronger signal above threshold, or HOLD/AVOID.
    """
    close = indicators.get("close")
    ma20 = indicators.get("ma20")
    ma50 = indicators.get("ma50")
    rsi = indicators.get("rsi")
    atr = indicators.get("atr")
    volume_ratio = indicators.get("volume_ratio")
    ma20_slope = indicators.get("ma20_slope")
    macd_hist = indicators.get("macd_hist")
    ma20_dist = indicators.get("ma20_distance_pct")
    above_ma20 = indicators.get("above_ma20", False)
    above_ma50 = indicators.get("above_ma50", False)
    volatility = indicators.get("volatility_20d")

    # ── AVOID gates ──────────────────────────────────────────────────
    if close is None or ma20 is None or rsi is None or atr is None:
        return _avoid(ticker, market, indicators, ["Insufficient indicator data — cannot score"])

    if volume_ratio is not None and volume_ratio < 0.3:
        return _avoid(ticker, market, indicators, ["Extremely low volume — possibly illiquid or suspended"])

    if volatility and volatility > EXTREME_VOLATILITY:
        return _avoid(ticker, market, indicators, [f"Annualized volatility {volatility:.0f}% is extreme — avoid"])

    # ── BUY_WATCHLIST scoring ────────────────────────────────────────
    buy_score = 0
    buy_reasons: list[str] = []

    if above_ma20:
        buy_score += 20
        buy_reasons.append("Price is above MA20 (short-term uptrend)")
    if above_ma50:
        buy_score += 20
        buy_reasons.append("Price is above MA50 (medium-term uptrend)")
    if RSI_BUY_LOW <= (rsi or 0) <= RSI_BUY_HIGH:
        buy_score += 20
        buy_reasons.append(f"RSI {rsi:.1f} — bullish range, not overbought")
    elif rsi and rsi > RSI_BUY_HIGH:
        buy_score -= 5  # overbought penalty
    if volume_ratio and volume_ratio >= MIN_VOLUME_RATIO:
        buy_score += 20
        buy_reasons.append(f"Volume is {volume_ratio:.1f}× the 20-day average")
    if ma20_slope and ma20_slope > 0:
        buy_score += 10
        buy_reasons.append("MA20 is sloping upward")
    if macd_hist and macd_hist > 0:
        buy_score += 10
        buy_reasons.append("MACD histogram is positive — bullish momentum")
    if ma20_dist is not None and abs(ma20_dist) <= MAX_MA20_DIST_PCT:
        buy_score += 5
        buy_reasons.append(f"Price within {MAX_MA20_DIST_PCT:.0f}% of MA20 — not overextended")
    elif ma20_dist and ma20_dist > MAX_MA20_DIST_PCT:
        buy_score -= 10
        buy_reasons.append(f"Price {ma20_dist:.1f}% above MA20 — possibly extended")

    buy_rc = compute_risk_control(close, atr, "BUY_WATCHLIST")
    if buy_rc and buy_rc.risk_reward >= MIN_RISK_REWARD:
        buy_score += 5
        buy_reasons.append(f"Risk/Reward {buy_rc.risk_reward:.1f} — favorable")
    elif buy_rc:
        buy_score -= 5

    # ── SELL_WARNING scoring ─────────────────────────────────────────
    sell_score = 0
    sell_reasons: list[str] = []

    if not above_ma20:
        sell_score += 25
        sell_reasons.append("Price is below MA20")
    if not above_ma50:
        sell_score += 15
        sell_reasons.append("Price is below MA50")
    if rsi and rsi < RSI_SELL_MAX:
        sell_score += 25
        sell_reasons.append(f"RSI {rsi:.1f} — weak/bearish territory")
    if ma20_slope and ma20_slope < 0:
        sell_score += 20
        sell_reasons.append("MA20 slope is declining")
    if macd_hist and macd_hist < 0:
        sell_score += 15
        sell_reasons.append("MACD histogram negative — bearish momentum")
    if volume_ratio and volume_ratio >= 1.5 and not above_ma20:
        sell_score += 15
        sell_reasons.append("High-volume move on the downside — distribution signal")

    sell_rc = compute_risk_control(close, atr, "SELL_WARNING")

    # ── Decision ─────────────────────────────────────────────────────
    logger.debug(f"{ticker}: buy_score={buy_score}, sell_score={sell_score}")

    if buy_score >= 55 and (buy_rc and buy_rc.risk_reward >= MIN_RISK_REWARD):
        return Signal(
            ticker=ticker,
            signal_type=SignalType.BUY_WATCHLIST,
            confidence=min(buy_score + 5, 95),
            reasons=buy_reasons,
            invalidation_conditions=[
                f"Daily close falls below MA20 ({ma20:.2f})",
                "High-volume bearish candle confirming breakdown",
            ],
            risk_control=buy_rc,
            indicators=indicators,
            market=market,
        )

    if sell_score >= 55:
        return Signal(
            ticker=ticker,
            signal_type=SignalType.SELL_WARNING,
            confidence=min(sell_score + 5, 95),
            reasons=sell_reasons,
            invalidation_conditions=[
                f"Daily close recovers above MA20 ({ma20:.2f})",
                "RSI recovers above 50 on strong volume",
            ],
            risk_control=sell_rc,
            indicators=indicators,
            market=market,
        )

    mixed_reasons = ["Mixed signals — no clear directional edge"]
    if buy_reasons:
        mixed_reasons += buy_reasons[:2]
    return Signal(
        ticker=ticker,
        signal_type=SignalType.HOLD,
        confidence=max(40, min(buy_score, sell_score)),
        reasons=mixed_reasons,
        indicators=indicators,
        market=market,
    )


def _avoid(ticker: str, market: str, indicators: dict, reasons: list[str]) -> Signal:
    return Signal(
        ticker=ticker,
        signal_type=SignalType.AVOID,
        confidence=0,
        reasons=reasons,
        indicators=indicators,
        market=market,
    )
