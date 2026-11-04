from typing import Literal, Optional
from pydantic import BaseModel, Field


class OrderFlowTriggerEvaluation(BaseModel):
    plan_aligned: bool = Field(
        description="True if current market structure matches one of the daily plan scenarios"
    )
    matched_scenario: Optional[str] = Field(
        default=None,
        description="Name or ID of the matched scenario (e.g. Scenario_A)"
    )
    in_key_zone: bool = Field(
        description="True if price is currently inside or testing a key zone (VAH/VAL/POC or Bookmap wall)"
    )
    zone_description: str = Field(
        description="Description of the zone currently being tested"
    )
    trigger_detected: bool = Field(
        description="True if an explicit Footprint absorption or Bookmap liquidity sweep trigger is observed"
    )
    trigger_description: str = Field(
        description="Specific observation on Footprint delta/absorption or Bookmap heatmap order book activity"
    )
    direction: Literal["BUY", "SELL", "NONE"] = Field(
        description="Trade bias if triggered, otherwise NONE"
    )
    trade_ready: bool = Field(
        description="True ONLY if plan_aligned=true AND in_key_zone=true AND trigger_detected=true"
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        default="MEDIUM",
        description="Confidence in order flow signal clarity"
    )
    suggested_entry: float = Field(
        description="Exact price level suggested for entry"
    )
    suggested_sl: float = Field(
        description="Exact Stop Loss level based on order flow invalidation"
    )
    suggested_tp: float = Field(
        description="Exact Take Profit target level"
    )
    summary: str = Field(
        description="Concise 1-2 sentence actionable reason for trader"
    )


def get_orderflow_trigger_json_schema() -> dict:
    return OrderFlowTriggerEvaluation.model_json_schema()

