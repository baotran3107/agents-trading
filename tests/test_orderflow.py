from src.analyzer.orderflow_models import (
    OrderFlowTriggerEvaluation,
    get_orderflow_trigger_json_schema,
)
from src.planner.models import DailyPlan, KeyZone, TradingScenario, get_daily_plan_json_schema


def test_daily_plan_schema():
    plan_data = {
        "date": "2026-11-04",
        "symbol": "XAUUSD",
        "market_context": "Balanced Auction inside Value Area",
        "primary_bias": "BULLISH",
        "key_zones": [
            {
                "name": "VAL Support",
                "price_low": 2695.0,
                "price_high": 2697.0,
                "zone_type": "SUPPORT",
                "description": "Previous day Value Area Low + Bookmap Buy Wall",
            }
        ],
        "scenarios": [
            {
                "scenario_id": "Scenario_A",
                "name": "VAL Sweep & Footprint Absorption",
                "bias": "BULLISH",
                "entry_condition": "Sweep below 2695",
                "trigger_signal": "Delta absorption wick + pop back into Value Area",
                "target_zone": "POC at 2710",
                "invalidation": "Acceptance below 2690 with aggressive selling",
            }
        ],
        "summary": "Look for longs around 2695 if Bookmap wall holds and Footprint absorbs sellers.",
        "generated_at": "2026-11-04T08:00:00",
    }
    plan = DailyPlan.model_validate(plan_data)
    assert plan.date == "2026-11-04"
    assert len(plan.key_zones) == 1
    assert len(plan.scenarios) == 1
    assert get_daily_plan_json_schema() is not None


def test_orderflow_trigger_evaluation():
    eval_data = {
        "plan_aligned": True,
        "matched_scenario": "Scenario_A",
        "in_key_zone": True,
        "zone_description": "Testing VAL support at 2696.00",
        "trigger_detected": True,
        "trigger_description": "Footprint shows 320 contracts absorbed at 2695.50 with +85 delta wick",
        "direction": "BUY",
        "trade_ready": True,
        "confidence": "HIGH",
        "suggested_entry": 2696.50,
        "suggested_sl": 2694.00,
        "suggested_tp": 2710.00,
        "summary": "Sellers trapped at VAL; absorption confirmed on Footprint.",
    }
    evaluation = OrderFlowTriggerEvaluation.model_validate(eval_data)
    assert evaluation.trade_ready is True
    assert evaluation.direction == "BUY"
    assert evaluation.suggested_entry == 2696.50

