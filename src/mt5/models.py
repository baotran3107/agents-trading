from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CandleData(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: Optional[int] = 0


class RawPrices(BaseModel):
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    current_price: float
    m15_high: float
    m15_low: float
    last_5m_candle: Optional[CandleData] = None

