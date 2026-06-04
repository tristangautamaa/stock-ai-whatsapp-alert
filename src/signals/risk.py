from loguru import logger
from .schemas import RiskControl


def compute_risk_control(
    close: float,
    atr: float,
    signal_type: str,
    atr_stop_mult: float = 2.0,
    atr_target_mult: float = 3.5,
) -> RiskControl | None:
    """
    ATR-based entry, stop loss, and target computation.
    Returns None when inputs are invalid or ATR is zero.
    """
    if not close or not atr or atr <= 0:
        logger.debug("Skipping risk control — invalid close or ATR")
        return None

    if signal_type == "BUY_WATCHLIST":
        entry_low = round(close * 0.99, 4)
        entry_high = round(close * 1.01, 4)
        stop_loss = round(close - atr_stop_mult * atr, 4)
        target = round(close + atr_target_mult * atr, 4)
    elif signal_type == "SELL_WARNING":
        entry_low = round(close * 0.99, 4)
        entry_high = round(close, 4)
        stop_loss = round(close + atr_stop_mult * atr, 4)
        target = round(close - atr_target_mult * atr, 4)
    else:
        return None

    risk = abs(close - stop_loss)
    reward = abs(target - close)
    rr = round(reward / risk, 2) if risk > 0 else 0.0

    return RiskControl(
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        target=target,
        risk_reward=rr,
        atr=round(atr, 4),
    )
