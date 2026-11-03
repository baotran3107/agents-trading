from datetime import datetime, timedelta
import pytest
from src.analyzer.models import ArgonAnalysisResult, ConditionResult
from src.config import RiskConfig
from src.decision.models import AgentState
from src.decision.risk import RiskCalculator
from src.decision.state_machine import SignalStateMachine
from src.mt5.models import RawPrices


@pytest.fixture
def state_machine():
    checklist_config = {
        "conditions": [
            {"id": "c1", "name": "Trend", "required": True},
            {"id": "c2", "name": "Level", "required": True},
            {"id": "c3", "name": "Candle", "required": True},
            {"id": "c4", "name": "Space", "required": False},
        ],
        "ready_threshold_ratio": 1.0,
        "watch_threshold_ratio": 0.75,
    }
    risk_calc = RiskCalculator(RiskConfig())
    return SignalStateMachine(checklist_config, risk_calc, cooldown_minutes=15)


def test_state_machine_ready(state_machine):
    now = datetime.now()
    analysis = ArgonAnalysisResult(
        direction="BUY",
        checklist=[
            ConditionResult(condition_id="c1", description="Trend", met=True, reason="Up"),
            ConditionResult(condition_id="c2", description="Level", met=True, reason="Support"),
            ConditionResult(condition_id="c3", description="Candle", met=True, reason="Hammer"),
            ConditionResult(condition_id="c4", description="Space", met=True, reason="Open room"),
        ],
        confidence="HIGH",
        summary="All rules aligned.",
    )
    prices = RawPrices(
        symbol="XAUUSD", timestamp=now, bid=2700, ask=2700.2, current_price=2700,
        m15_high=2720, m15_low=2690
    )

    decision = state_machine.evaluate("cycle_1", now, analysis, prices)
    assert decision.state == AgentState.READY
    assert decision.direction == "BUY"
    assert decision.is_suppressed_by_cooldown is False


def test_state_machine_watch(state_machine):
    now = datetime.now()
    analysis = ArgonAnalysisResult(
        direction="BUY",
        checklist=[
            ConditionResult(condition_id="c1", description="Trend", met=True, reason="Up"),
            ConditionResult(condition_id="c2", description="Level", met=True, reason="Support"),
            ConditionResult(condition_id="c3", description="Candle", met=False, reason="Still forming"),
            ConditionResult(condition_id="c4", description="Space", met=True, reason="Open room"),
        ],
        confidence="MEDIUM",
        summary="Almost ready.",
    )
    prices = RawPrices(
        symbol="XAUUSD", timestamp=now, bid=2700, ask=2700.2, current_price=2700,
        m15_high=2720, m15_low=2690
    )

    decision = state_machine.evaluate("cycle_2", now, analysis, prices)
    assert decision.state == AgentState.WATCH
    assert decision.direction == "BUY"


def test_state_machine_cooldown(state_machine):
    now = datetime.now()
    analysis = ArgonAnalysisResult(
        direction="BUY",
        checklist=[
            ConditionResult(condition_id="c1", description="Trend", met=True, reason="Up"),
            ConditionResult(condition_id="c2", description="Level", met=True, reason="Support"),
            ConditionResult(condition_id="c3", description="Candle", met=True, reason="Hammer"),
            ConditionResult(condition_id="c4", description="Space", met=True, reason="Open room"),
        ],
        confidence="HIGH",
        summary="Ready.",
    )
    prices = RawPrices(
        symbol="XAUUSD", timestamp=now, bid=2700, ask=2700.2, current_price=2700,
        m15_high=2720, m15_low=2690
    )

    # First trigger
    d1 = state_machine.evaluate("cycle_1", now, analysis, prices)
    assert d1.is_suppressed_by_cooldown is False

    # Second trigger 5 minutes later (within 15m cooldown)
    later = now + timedelta(minutes=5)
    d2 = state_machine.evaluate("cycle_2", later, analysis, prices)
    assert d2.is_suppressed_by_cooldown is True

