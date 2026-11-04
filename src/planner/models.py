from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class KeyZone(BaseModel):
    name: str = Field(description="Name of the zone, e.g., VAH, VAL, POC, Bookmap Wall at 2700")
    price_low: float = Field(description="Lower boundary of the price zone")
    price_high: float = Field(description="Upper boundary of the price zone")
    zone_type: Literal["SUPPORT", "RESISTANCE", "POC", "LIQUIDITY_POOL"] = Field(
        description="Type of order flow zone"
    )
    description: str = Field(description="Brief note on why this level matters (VP high volume or Bookmap resting orders)")


class TradingScenario(BaseModel):
    scenario_id: str = Field(description="e.g. Scenario_A, Scenario_B")
    name: str = Field(description="Descriptive name of the play, e.g., 'VAL Liquidity Sweep & Long'")
    bias: Literal["BULLISH", "BEARISH"] = Field(description="Trade direction")
    entry_condition: str = Field(description="What market must do first (e.g. test support, sweep resting liquidity)")
    trigger_signal: str = Field(description="Footprint or Bookmap confirmation required (e.g., absorption, delta flip, CVD divergence)")
    target_zone: str = Field(description="Expected Take Profit target")
    invalidation: str = Field(description="Level or behavior that cancels this scenario")


class DailyPlan(BaseModel):
    date: str = Field(description="Date of the plan (YYYY-MM-DD)")
    symbol: str = Field(default="XAUUSD", description="Symbol traded")
    market_context: str = Field(description="Auction Market state (e.g. Balanced rotation, Trend day, Value area rejection)")
    primary_bias: Literal["BULLISH", "BEARISH", "NEUTRAL_RANGE"] = Field(
        description="Overall market bias for the day"
    )
    key_zones: List[KeyZone] = Field(description="List of key Volume Profile and Bookmap levels")
    scenarios: List[TradingScenario] = Field(description="Specific trade setups to watch for today")
    summary: str = Field(description="Actionable 2-3 sentence overview for the trader today")
    generated_at: str = Field(description="Timestamp when plan was generated")


def get_daily_plan_json_schema() -> dict:
    return DailyPlan.model_json_schema()

