import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from src.analyzer.argon_client import ArgonClient
from src.capture.screen_capture import ScreenCaptureService
from src.config import AppConfig
from src.mt5.client import BaseMT5Client
from src.planner.models import DailyPlan, get_daily_plan_json_schema

logger = logging.getLogger(__name__)


class DailyPlanner:
    def __init__(
        self,
        config: AppConfig,
        analyzer: ArgonClient,
        capture_service: ScreenCaptureService,
        mt5_client: BaseMT5Client,
    ):
        self.config = config
        self.analyzer = analyzer
        self.capture_service = capture_service
        self.mt5_client = mt5_client
        self.plan_file = Path(config.daily_plan.plan_file)
        self.plan_file.parent.mkdir(parents=True, exist_ok=True)
        self.current_plan: Optional[DailyPlan] = self.load_active_plan()

    def load_active_plan(self) -> Optional[DailyPlan]:
        if not self.plan_file.exists():
            return None
        try:
            with open(self.plan_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            plan = DailyPlan.model_validate(data)
            self.current_plan = plan
            return plan
        except Exception as e:
            logger.error(f"Failed to load daily plan: {e}")
            return None

    def generate_plan(self) -> Optional[DailyPlan]:
        """
        Captures dual-monitor setup (Left: VP & Footprint, Right: Bookmap)
        and calls Argon to synthesize the Daily Trading Plan.
        """
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Generating Daily Plan for {self.config.trading.symbol}...")

        # 1. Capture dual-screen
        image_path = self.capture_service.capture(filename=f"daily_plan_{timestamp_str}.png")

        # 2. Fetch MT5 reference prices
        try:
            raw_prices = self.mt5_client.get_raw_prices(self.config.trading.symbol)
            price_context = (
                f"Current Price: {raw_prices.current_price:.2f}, "
                f"M15 High: {raw_prices.m15_high:.2f}, M15 Low: {raw_prices.m15_low:.2f}"
            )
        except Exception as e:
            price_context = "MT5 live price unavailable."

        # 3. Prompt for Order Flow Daily Plan
        schema_str = json.dumps(get_daily_plan_json_schema())
        prompt = f"""You are an elite institutional Order Flow and Auction Market Theory trader analyzing gold ({self.config.trading.symbol}).

Inspect the composite dual-monitor chart at: {image_path.resolve()}
- LEFT MONITOR: Volume Profile (VP) structure (Value Area High/Low, Point of Control POC, Low Volume Nodes LVN) and Footprint chart (Delta, imbalances, absorptions).
- RIGHT MONITOR: Bookmap (Resting limit order liquidity heatmap, CVD, aggressive market bubbles, liquidity walls).
- REFERENCE PRICES: {price_context}

YOUR TASK:
Formulate today's trading plan adhering to the JSON schema:
1. Identify the Market Context (e.g. Balanced rotation inside value area, Imbalanced trend extension, or Liquidity sweep mode).
2. Mark Key Zones: VAH, VAL, POC, and major Bookmap resting liquidity clusters.
3. Formulate 1 or 2 specific actionable Trading Scenarios (e.g. Scenario A: Buy on VAL sweep + Footprint absorption; Scenario B: Fade at resting liquidity ceiling).
4. For each scenario, clearly specify what Footprint / Bookmap trigger confirms entry and what invalidates it.
5. Return strictly in JSON according to the schema.
"""

        cmd = [
            self.config.model.cli_path,
            "-p", prompt,
            "--model", self.config.model_name,
            "--disable-slash-commands",
            "--output-format", "json",
            "--json-schema", schema_str,
        ]

        try:
            import subprocess
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
            if proc.returncode != 0:
                logger.error(f"Plan generation CLI error: {proc.stderr or proc.stdout}")
                return None

            cli_output = json.loads(proc.stdout)
            data = cli_output.get("structured_output") or cli_output.get("response")

            if isinstance(data, str):
                from src.analyzer.validator import extract_json_from_text
                data = extract_json_from_text(data)

            plan = DailyPlan.model_validate(data)
            self.current_plan = plan

            # Persist plan
            with open(self.plan_file, "w", encoding="utf-8") as f:
                f.write(plan.model_dump_json(indent=2))

            logger.info("Daily Plan successfully generated and saved.")
            return plan

        except Exception as e:
            logger.error(f"Failed to generate daily plan: {e}", exc_info=True)
            return None

    def format_plan_message(self, plan: DailyPlan) -> str:
        """Formats the Daily Plan into clean Telegram Markdown."""
        bias_emoji = {
            "BULLISH": "🟢 BULLISH",
            "BEARISH": "🔴 BEARISH",
            "NEUTRAL_RANGE": "⚪ NEUTRAL / RANGE ROTATION",
        }.get(plan.primary_bias, plan.primary_bias)

        lines = [
            f"📋 **DAILY TRADING PLAN — {plan.symbol}**",
            f"📅 Date: `{plan.date}` | Bias: **{bias_emoji}**",
            f"🏛 *Auction Context:* {plan.market_context}",
            "",
            "🎯 **Key Order Flow Zones (VP & Bookmap):**",
        ]

        for z in plan.key_zones:
            lines.append(f"• **{z.name}** (`{z.price_low:.1f} - {z.price_high:.1f}`): {z.description}")

        lines.append("\n⚡ **Planned Scenarios for Today:**")
        for s in plan.scenarios:
            dir_icon = "🟢" if s.bias == "BULLISH" else "🔴"
            lines.extend([
                f"{dir_icon} **{s.name}** ({s.bias}):",
                f"   • *Condition:* {s.entry_condition}",
                f"   • *Trigger:* {s.trigger_signal}",
                f"   • *Target:* {s.target_zone}",
                f"   • *Invalidation:* {s.invalidation}",
            ])

        lines.extend([
            "",
            f"💡 *Summary:* {plan.summary}",
            "\n_Bot will monitor 5M candles at T-15s against these exact scenarios._"
        ])

        return "\n".join(lines)

