import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer.argon_client import ArgonClient
from src.capture.screen_capture import (
    BlackImageError,
    CaptureError,
    ScreenCaptureService,
    WindowNotFoundError,
)
from src.config import AppConfig, load_config
from src.decision.models import AgentState, SignalDecision
from src.decision.recheck import CandleCloseVerifier
from src.decision.risk import RiskCalculator
from src.decision.state_machine import SignalStateMachine
from src.mt5.client import MT5ConnectionError, get_mt5_client
from src.notifier.telegram_bot import TelegramNotifier
from src.planner.daily_planner import DailyPlanner
from src.storage.logger import CycleStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("TradingAgent")


def get_seconds_until_next_t_minus(timeframe_minutes: int = 5, t_minus_seconds: int = 10) -> float:
    """
    Computes exact seconds to sleep until the next cycle trigger (e.g. 10s before 5M candle close).
    """
    now = datetime.now()
    total_seconds_in_hour = now.minute * 60 + now.second + (now.microsecond / 1_000_000.0)
    interval_seconds = timeframe_minutes * 60

    # Next boundary where candle closes
    current_interval_index = int(total_seconds_in_hour // interval_seconds)
    next_close_seconds = (current_interval_index + 1) * interval_seconds
    target_seconds = next_close_seconds - t_minus_seconds

    diff = target_seconds - total_seconds_in_hour
    if diff <= 0:
        # If we are already past T-10s for this candle, schedule for the next candle
        next_close_seconds = (current_interval_index + 2) * interval_seconds
        target_seconds = next_close_seconds - t_minus_seconds
        diff = target_seconds - total_seconds_in_hour

    return max(0.1, diff)


def is_within_active_hours(config: AppConfig) -> bool:
    """Checks if current time falls within configured trading window (FR-1 / ST-002 AC-3)."""
    ah = config.trading.active_hours
    if not ah.enabled:
        return True

    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(ah.timezone)
        now = datetime.now(tz)
    except Exception:
        now = datetime.now()

    current_time_str = now.strftime("%H:%M")
    return ah.start <= current_time_str <= ah.end


class TradingSignalAgent:
    def __init__(self, config: AppConfig, checklist_path: Optional[Path] = None):
        self.config = config
        self.checklist_path = checklist_path or (
            Path(__file__).resolve().parent.parent / "config" / "checklist.json"
        )
        with open(self.checklist_path, "r", encoding="utf-8") as f:
            self.checklist_config = json.load(f)

        # Initialize sub-services
        self.storage = CycleStorage(
            db_path=config.storage.db_path,
            jsonl_path=config.storage.log_file,
        )
        self.notifier = TelegramNotifier(config.telegram, self.storage)
        self.capture_service = ScreenCaptureService(
            output_dir=config.capture.output_dir,
            window_title=config.capture.window_title,
            black_threshold=config.capture.black_threshold,
        )
        self.mt5_client = get_mt5_client(config.mt5)
        self.analyzer = ArgonClient(config.model)
        self.risk_calculator = RiskCalculator(config.risk)
        self.state_machine = SignalStateMachine(
            checklist_config=self.checklist_config,
            risk_calculator=self.risk_calculator,
            cooldown_minutes=config.telegram.cooldown_minutes,
        )
        self.recheck_verifier = CandleCloseVerifier(self.mt5_client)
        self.daily_planner = DailyPlanner(
            config=config,
            analyzer=self.analyzer,
            capture_service=self.capture_service,
        )
        self.notifier.on_plan_requested = self.trigger_daily_plan
        self.last_plan_date: Optional[str] = (
            self.daily_planner.current_plan.date if self.daily_planner.current_plan else None
        )

    def trigger_daily_plan(self) -> None:
        """Triggers Daily Plan generation on-demand or at 08:00 AM."""
        logger.info("Executing Daily Plan generation...")
        plan = self.daily_planner.generate_plan()
        if plan:
            self.last_plan_date = plan.date
            # Capture snapshot to attach with plan
            latest_img = Path(self.config.capture.output_dir) / f"daily_plan_active.png"
            if not latest_img.exists():
                latest_img = None
            self.notifier.send_daily_plan(plan, latest_img)
            logger.info(f"Daily Plan {plan.date} generated and sent to Telegram.")
        else:
            self.notifier.send_system_alert("⚠️ Không thể tạo Daily Plan tự động. Vui lòng kiểm tra màn hình và agy CLI.")

    def check_daily_plan_schedule(self) -> None:
        """Auto-triggers plan at 08:00 AM local time if not already created today."""
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        current_time_str = now.strftime("%H:%M")

        target_time = self.config.daily_plan.plan_time  # "08:00"
        if self.config.daily_plan.auto_generate:
            if current_time_str >= target_time and self.last_plan_date != today_str:
                logger.info(f"08:00 AM Daily Plan trigger reached for {today_str}.")
                self.trigger_daily_plan()

    def startup(self) -> None:
        logger.info("Initializing Trading Signal Agent...")
        try:
            self.mt5_client.connect()
        except Exception as e:
            logger.warning(f"MT5 initial connection warning: {e}")

        if self.notifier.is_configured:
            self.notifier.send_text("🚀 **Trading Signal Agent Initialized & Active**")

    def run_single_cycle(self) -> Optional[SignalDecision]:
        """Executes one full analysis cycle (T-10s -> Candle Close)."""
        cycle_timestamp = datetime.now()
        cycle_id = cycle_timestamp.strftime("%Y%m%d_%H%M%S")
        symbol = self.config.trading.symbol

        logger.info(f"=== Starting Cycle {cycle_id} for {symbol} (T-10s) ===")

        # Check trading hours (FR-1 / ST-002 AC-3)
        if not is_within_active_hours(self.config):
            logger.info("Current time is outside configured active trading hours. Skipping cycle.")
            return None

        # ST-002: Screen Capture
        image_path: Optional[Path] = None
        try:
            image_path = self.capture_service.capture(filename=f"chart_{cycle_id}.png")
        except BlackImageError as e:
            logger.error(f"ST-002 AC-2: Black image detected: {e}")
            self.notifier.send_system_alert(f"Chart capture failed: Black/blank image detected.")
            return None
        except WindowNotFoundError as e:
            logger.error(f"ST-002 AC-2: Target window not found: {e}")
            self.notifier.send_system_alert(f"Chart window not found: {e}")
            return None
        except CaptureError as e:
            logger.error(f"ST-002 Capture error: {e}")
            self.notifier.send_system_alert(f"Chart capture failed: {e}")
            return None

        # Order Flow Analysis against Active Daily Plan (T-15s) solely from captured screens
        of_eval, meta = self.analyzer.analyze_orderflow_cycle(
            image_path=image_path,
            daily_plan=self.daily_planner.current_plan,
        )

        telegram_msg_id = None
        recheck_status = None

        if of_eval and of_eval.trade_ready:
            logger.info(
                f"🚨 ORDER FLOW TRIGGER MET: {of_eval.direction} | "
                f"Scenario: {of_eval.matched_scenario} | Zone: {of_eval.zone_description}"
            )
            # Calculate Risk Parameters ($250 fixed risk) directly from Order Flow levels
            trade_params = self.risk_calculator.calculate_orderflow_parameters(
                direction=of_eval.direction,
                entry=of_eval.suggested_entry,
                sl=of_eval.suggested_sl,
                tp=of_eval.suggested_tp,
            )

            # Send Proposal to Telegram
            telegram_msg_id = self.notifier.send_orderflow_trade_request(
                eval_result=of_eval,
                trade_params=trade_params,
                image_path=image_path,
                cycle_id=cycle_id,
                symbol=symbol,
            )

            # ST-008 & FR-11: Re-check at Candle Close (T=0)
            logger.info(f"Waiting {self.config.trading.t_minus_seconds}s until 5M candle officially closes...")
            time.sleep(self.config.trading.t_minus_seconds)

            decision_stub = SignalDecision(
                cycle_id=cycle_id,
                timestamp=cycle_timestamp,
                state=AgentState.READY,
                direction=of_eval.direction,
                analysis=None,
                trade_params=trade_params,
            )
            recheck = self.recheck_verifier.verify_at_candle_close(
                decision=decision_stub,
                symbol=symbol,
                timeframe_minutes=self.config.trading.timeframe_minutes,
            )
            recheck_status = recheck.status_label
            logger.info(f"Candle Close Recheck: {recheck.status_label} - {recheck.reason}")
            self.notifier.send_recheck_outcome(decision_stub, recheck, symbol)

            decision = decision_stub
        else:
            reason_msg = of_eval.summary if of_eval else "Order flow evaluation did not trigger."
            logger.info(f"Order Flow Monitor: No trigger met ({reason_msg})")
            decision = SignalDecision(
                cycle_id=cycle_id,
                timestamp=cycle_timestamp,
                state=AgentState.IDLE,
                direction="NONE",
                analysis=None,
                reasons=[reason_msg],
            )

        # ST-007: Record cycle to SQLite and JSONL
        self.storage.record_cycle(
            decision=decision,
            symbol=symbol,
            image_path=str(image_path) if image_path else None,
            telegram_message_id=telegram_msg_id,
            recheck_status=recheck_status,
        )

        return decision

    def start_loop(self) -> None:
        """Main service loop running every 5 minutes at T-10s."""
        self.startup()
        logger.info("Trading Signal Agent main loop running. Waiting for cycle triggers...")

        while True:
            try:
                # Check 08:00 AM daily plan auto-generation
                self.check_daily_plan_schedule()

                # Poll Telegram commands & feedback buttons continuously
                self.notifier.process_updates()

                # Calculate sleep duration to next T-10s trigger
                seconds_to_wait = get_seconds_until_next_t_minus(
                    timeframe_minutes=self.config.trading.timeframe_minutes,
                    t_minus_seconds=self.config.trading.t_minus_seconds,
                )

                # Check heartbeat (ST-007 AC-2)
                if not self.storage.check_heartbeat(
                    max_idle_minutes=self.config.storage.heartbeat_timeout_minutes
                ):
                    logger.warning("Heartbeat alert: No successful cycle recorded in 15 minutes.")
                    self.notifier.send_system_alert(
                        "⚠️ Heartbeat warning: No successful cycle in 15 minutes."
                    )

                # Sleep in small slices to remain responsive to Telegram updates
                while seconds_to_wait > 2.0:
                    time.sleep(2.0)
                    self.notifier.process_updates()
                    seconds_to_wait = get_seconds_until_next_t_minus(
                        timeframe_minutes=self.config.trading.timeframe_minutes,
                        t_minus_seconds=self.config.trading.t_minus_seconds,
                    )

                if seconds_to_wait > 0:
                    time.sleep(seconds_to_wait)

                # Trigger cycle!
                self.run_single_cycle()

            except KeyboardInterrupt:
                logger.info("Graceful shutdown requested by user.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                time.sleep(5.0)


def main():
    parser = argparse.ArgumentParser(description="Trading Signal Agent")
    parser.add_argument("--once", action="store_true", help="Run a single 5M cycle and exit")
    parser.add_argument("--plan", action="store_true", help="Generate Daily Plan immediately and exit")
    parser.add_argument("--config", type=str, default="config/config.yaml", help="Path to config YAML")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    agent = TradingSignalAgent(cfg)

    if args.plan:
        agent.startup()
        agent.trigger_daily_plan()
        print("\nDaily Plan generated successfully.")
    elif args.once:
        agent.startup()
        decision = agent.run_single_cycle()
        print(f"\nCycle completed. State: {decision.state if decision else 'None'}")
    else:
        agent.start_loop()


if __name__ == "__main__":
    main()

