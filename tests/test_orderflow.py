from src.analyzer.orderflow_models import (
    OrderFlowTriggerEvaluation,
    get_orderflow_trigger_json_schema,
)
from src.planner.models import DailyPlan, PlanItem, get_daily_plan_json_schema


def test_daily_plan_schema():
    plan_data = {
        "date": "06/11/2026",
        "symbol": "XAUUSD",
        "overview": "Vàng giằng co quanh POC 2700, ưu tiên canh phản ứng tại biên Value Area.",
        "plans": [
            {
                "plan_number": 1,
                "bias": "BUY",
                "wait_zone_low": 2695.0,
                "wait_zone_high": 2697.0,
                "entry_condition": "Quét thanh khoản VAL và tường mua Bookmap, Footprint có râu hấp thụ và delta dương",
            },
            {
                "plan_number": 2,
                "bias": "SELL",
                "wait_zone_low": 2715.0,
                "wait_zone_high": 2717.0,
                "entry_condition": "Chạm VAH kháng cự, Bookmap cạn kiệt lực mua và Footprint xuất hiện mất cân bằng bán",
            },
        ],
        "generated_at": "2026-11-06T08:00:00",
    }
    plan = DailyPlan.model_validate(plan_data)
    assert plan.date == "06/11/2026"
    assert len(plan.plans) == 2
    assert plan.plans[0].bias == "BUY"
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

