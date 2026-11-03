from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel
from src.analyzer.models import ArgonAnalysisResult, ConditionResult


class AgentState(str, Enum):
    IDLE = "IDLE"
    WATCH = "WATCH"
    READY = "READY"


class TradeParameters(BaseModel):
    entry_price: float
    stop_loss: float
    take_profit: float
    sl_points: float
    risk_reward_ratio: float
    lot_size: float
    fixed_loss_usd: float


class SignalDecision(BaseModel):
    cycle_id: str
    timestamp: datetime
    state: AgentState
    direction: str  # BUY, SELL, NONE
    analysis: Optional[ArgonAnalysisResult]
    trade_params: Optional[TradeParameters] = None
    reasons: List[str] = []
    is_suppressed_by_cooldown: bool = False

