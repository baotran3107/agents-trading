import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from src.analyzer.models import ArgonAnalysisResult
from src.decision.models import AgentState, SignalDecision, TradeParameters
from src.decision.risk import RiskCalculator
from src.mt5.models import RawPrices

logger = logging.getLogger(__name__)


class SignalStateMachine:
    def __init__(
        self,
        checklist_config: Dict[str, Any],
        risk_calculator: RiskCalculator,
        cooldown_minutes: int = 15,
    ):
        self.checklist_config = checklist_config
        self.risk_calculator = risk_calculator
        self.cooldown_minutes = cooldown_minutes
        self.last_signal_time: Optional[datetime] = None
        self.last_signal_direction: Optional[str] = None
        self.last_signal_state: Optional[AgentState] = None

    def evaluate(
        self,
        cycle_id: str,
        timestamp: datetime,
        analysis: Optional[ArgonAnalysisResult],
        raw_prices: RawPrices,
    ) -> SignalDecision:
        """
        Determines IDLE / WATCH / READY based solely on code evaluation of checklist.
        FR-5: Only code decides the state; AI only fills in the checklist.
        """
        if not analysis or analysis.direction not in ("BUY", "SELL"):
            return SignalDecision(
                cycle_id=cycle_id,
                timestamp=timestamp,
                state=AgentState.IDLE,
                direction="NONE",
                analysis=analysis,
                reasons=["No actionable directional bias from AI."],
            )

        direction = analysis.direction
        checklist = analysis.checklist

        # Map condition rules
        configured_conditions = {
            c["id"]: c for c in self.checklist_config.get("conditions", [])
        }

        total_required = 0
        met_required = 0
        total_conditions = len(checklist)
        total_met = sum(1 for c in checklist if c.met)
        unmet_reasons = []

        for item in checklist:
            cfg = configured_conditions.get(item.condition_id, {})
            is_req = cfg.get("required", True)
            if is_req:
                total_required += 1
                if item.met:
                    met_required += 1
                else:
                    unmet_reasons.append(f"{item.condition_id}: {item.reason}")
            elif not item.met:
                unmet_reasons.append(f"[Optional] {item.condition_id}: {item.reason}")

        ready_threshold = self.checklist_config.get("ready_threshold_ratio", 1.0)
        watch_threshold = self.checklist_config.get("watch_threshold_ratio", 0.75)

        # Decide state
        all_required_met = (total_required > 0 and met_required == total_required)
        ratio = total_met / max(1, total_conditions)

        if all_required_met and ratio >= ready_threshold:
            state = AgentState.READY
            reasons = ["All required trading checklist conditions are met."]
        elif ratio >= watch_threshold:
            state = AgentState.WATCH
            reasons = [
                f"Near setup ({total_met}/{total_conditions} conditions met). Early heads-up.",
                *unmet_reasons,
            ]
        else:
            state = AgentState.IDLE
            reasons = [
                f"Insufficient conditions met ({total_met}/{total_conditions}).",
                *unmet_reasons,
            ]

        # Calculate trade parameters if WATCH or READY
        trade_params = None
        if state in (AgentState.WATCH, AgentState.READY):
            trade_params = self.risk_calculator.calculate_trade_parameters(
                direction=direction, raw_prices=raw_prices
            )

        # Check cooldown (ST-005 AC-3)
        is_suppressed = False
        if state in (AgentState.WATCH, AgentState.READY):
            if (
                self.last_signal_time is not None
                and self.last_signal_direction == direction
                and self.last_signal_state == state
                and (timestamp - self.last_signal_time) < timedelta(minutes=self.cooldown_minutes)
            ):
                is_suppressed = True
                logger.info(
                    f"Signal {state.value} {direction} suppressed by cooldown "
                    f"({self.cooldown_minutes}m)."
                )
            else:
                self.last_signal_time = timestamp
                self.last_signal_direction = direction
                self.last_signal_state = state

        return SignalDecision(
            cycle_id=cycle_id,
            timestamp=timestamp,
            state=state,
            direction=direction,
            analysis=analysis,
            trade_params=trade_params,
            reasons=reasons,
            is_suppressed_by_cooldown=is_suppressed,
        )

