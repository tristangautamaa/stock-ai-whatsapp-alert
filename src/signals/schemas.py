from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class SignalType(str, Enum):
    BUY_WATCHLIST = "BUY_WATCHLIST"
    SELL_WARNING = "SELL_WARNING"
    HOLD = "HOLD"
    AVOID = "AVOID"


class RiskControl(BaseModel):
    entry_low: float
    entry_high: float
    stop_loss: float
    target: float
    risk_reward: float
    atr: Optional[float] = None


class Signal(BaseModel):
    ticker: str
    signal_type: SignalType
    confidence: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    risk_control: Optional[RiskControl] = None
    indicators: dict = Field(default_factory=dict)
    ai_explanation: Optional[str] = None
    sentiment_score: Optional[float] = None
    timegpt_forecast: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    market: str = "IDX"

    @property
    def is_actionable(self) -> bool:
        return self.signal_type in (SignalType.BUY_WATCHLIST, SignalType.SELL_WARNING)


class SignalRequest(BaseModel):
    """Inbound payload from a TradingView webhook alert."""
    ticker: str
    action: str = "neutral"
    price: Optional[float] = None
    message: Optional[str] = None
    strategy: Optional[str] = None
    timeframe: Optional[str] = "1D"
    extra: dict = Field(default_factory=dict)
