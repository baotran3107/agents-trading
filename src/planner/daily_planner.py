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
        mt5_client: Optional[BaseMT5Client] = None,
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

    def generate_plan(self, image_path: Optional[Path] = None) -> Optional[DailyPlan]:
        """
        Synthesizes the Daily Trading Plan via Argon.
        If image_path is None, captures dual-monitor setup (Left: VP & Footprint, Right: Bookmap).
        """
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Generating Daily Plan for {self.config.trading.symbol}...")

        # 1. Use provided image or capture dual-screen
        if image_path is None or not image_path.exists():
            image_path = self.capture_service.capture(filename=f"daily_plan_{timestamp_str}.png")
        else:
            logger.info(f"Using provided chart image for daily plan: {image_path}")

        # 2. Prompt for Order Flow Daily Plan
        schema_str = json.dumps(get_daily_plan_json_schema())
        today_date_str = datetime.now().strftime("%d/%m/%Y")
        prompt = f"""Bạn là một chuyên gia giao dịch định lượng theo phương pháp Order Flow và Auction Market Theory phân tích vàng ({self.config.trading.symbol}).

Quan sát kỹ hình ảnh biểu đồ 2 màn hình tại: {image_path.resolve()}
- MÀN HÌNH TRÁI: Cấu trúc Volume Profile (VAH, VAL, POC) và biểu đồ Footprint (Delta, cụm hấp thụ, mất cân bằng bid/ask).
- MÀN HÌNH PHẢI: Bookmap (Bản đồ nhiệt tường thanh khoản resting limit orders, CVD, bong bóng khớp lệnh chủ động).

NGUỒN DỮ LIỆU: Chỉ đọc và phân tích trực tiếp từ ảnh chụp 2 màn hình trên. Toàn bộ thang giá, cấu trúc Volume Profile và thanh khoản Bookmap đều quan sát trực tiếp từ biểu đồ (không dùng bất kỳ dữ liệu nào từ MT5).

QUY TẮC BẮT BUỘC VỀ NGÔN NGỮ VÀ NỘI DUNG:
1. TOÀN BỘ NỘI DUNG MÔ TẢ PHẢI ĐƯỢC VIẾT HOÀN TOÀN BẰNG TIẾNG VIỆT (STRICTLY VIETNAMESE).
2. 'date': Định dạng ngày bắt buộc là dd/mm/yyyy (ví dụ: '{today_date_str}').
3. 'overview': Tóm tắt bối cảnh thị trường trong ngày thật cô đọng, TỐI ĐA 100 KÝ TỰ bằng tiếng Việt.
4. 'plans': Tạo từ 2 đến 3 kế hoạch giao dịch (#Plan 1, #Plan 2, #Plan 3), mỗi plan gồm:
   - 'plan_number': 1, 2 hoặc 3
   - 'bias': 'BUY' hoặc 'SELL'
   - 'wait_zone_low': mức giá thấp của vùng chờ phản ứng
   - 'wait_zone_high': mức giá cao của vùng chờ phản ứng
   - 'entry_condition': điều kiện kích hoạt vào lệnh ngắn gọn súc tích theo Order Flow (Footprint, Bookmap) bằng tiếng Việt.
5. Trả về đúng định dạng JSON theo schema đã cung cấp.
"""

        cmd = [
            self.config.model.cli_path,
            "-p", prompt,
            "--model", self.config.model.model_name,
            "--disable-slash-commands",
            "--output-format", "json",
            "--json-schema", schema_str,
        ]

        try:
            import subprocess
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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

    @staticmethod
    def format_plan_message(plan: DailyPlan) -> str:
        """
        Formats the Daily Plan strictly according to content.md format:
        📅 Kế hoạch ngày {dd/mm/yyyy}
        📝 {Overview ≤100 ký tự}

        #Plan 1: {BUY/SELL}
        • Vùng chờ: {giá thấp} - {giá cao}
        • Điều kiện vào: {điều kiện}
        """
        lines = [
            f"📅 Kế hoạch ngày {plan.date}",
            f"📝 {plan.overview}",
            "",
        ]

        for p in plan.plans:
            lines.extend([
                f"#Plan {p.plan_number}: {p.bias}",
                f"• Vùng chờ: {p.wait_zone_low:.2f} - {p.wait_zone_high:.2f}",
                f"• Điều kiện vào: {p.entry_condition}",
                "",
            ])

        return "\n".join(lines).strip()

