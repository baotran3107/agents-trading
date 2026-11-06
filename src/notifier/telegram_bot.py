import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional
import httpx
from src.analyzer.models import ArgonAnalysisResult
from src.analyzer.orderflow_models import OrderFlowTriggerEvaluation
from src.config import TelegramConfig
from src.decision.models import AgentState, SignalDecision, TradeParameters
from src.decision.recheck import RecheckResult
from src.planner.models import DailyPlan
from src.storage.logger import CycleStorage

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, config: TelegramConfig, storage: CycleStorage):
        self.config = config
        self.storage = storage
        self.base_url = f"https://api.telegram.org/bot{self.config.bot_token}"
        self.is_paused = False
        self._last_update_id = 0
        self.on_plan_requested: Optional[Callable[[], Any]] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.config.enabled and self.config.bot_token and self.config.chat_id)

    def format_signal_caption(self, decision: SignalDecision, symbol: str) -> str:
        tag = (
            "🚨 **READY SIGNAL**"
            if decision.state == AgentState.READY
            else "👀 **WATCH ALERT (Early Heads-up)**"
        )
        dir_emoji = "🟢 BUY" if decision.direction == "BUY" else "🔴 SELL"

        lines = [
            f"{tag} — {symbol} ({dir_emoji})",
            "⚠️ *Sent 10 seconds BEFORE candle close*",
            "",
        ]

        if decision.trade_params:
            tp = decision.trade_params
            lines.extend([
                f"📊 **Trade Parameters ($250 Fixed Risk):**",
                f"• Entry: `{tp.entry_price:.2f}`",
                f"• Stop Loss: `{tp.stop_loss:.2f}` ({tp.sl_points:.1f} pts)",
                f"• Take Profit: `{tp.take_profit:.2f}` (1:{tp.risk_reward_ratio})",
                f"• Recommended Lot: `{tp.lot_size:.2f}`",
                "",
            ])

        if decision.analysis:
            lines.append("📋 **Plan Checklist Evaluation:**")
            for item in decision.analysis.checklist:
                status = "✅" if item.met else "❌"
                lines.append(f"{status} *{item.condition_id}*: {item.reason}")
            lines.append("")
            lines.append(f"💡 *Summary:* {decision.analysis.summary}")

        lines.append(f"\n_Cycle ID: {decision.cycle_id}_")
        return "\n".join(lines)

    def send_signal_alert(
        self, decision: SignalDecision, image_path: Optional[Path], symbol: str
    ) -> Optional[int]:
        if not self.is_configured:
            logger.info("Telegram not configured or disabled; skipping message.")
            return None

        if self.is_paused:
            logger.info("Telegram notifier is paused; skipping signal.")
            return None

        if decision.is_suppressed_by_cooldown:
            logger.info(f"Signal suppressed by cooldown for {symbol}.")
            return None

        caption = self.format_signal_caption(decision, symbol)
        cycle_id = decision.cycle_id

        # Inline feedback buttons for labeling (FR-10 / ST-006)
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Valid Plan Setup",
                        "callback_data": f"label:{cycle_id}:VALID",
                    },
                    {
                        "text": "❌ Misread / Invalid",
                        "callback_data": f"label:{cycle_id}:INVALID",
                    },
                ]
            ]
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                if image_path and image_path.exists():
                    url = f"{self.base_url}/sendPhoto"
                    with open(image_path, "rb") as photo_file:
                        files = {"photo": photo_file}
                        data = {
                            "chat_id": self.config.chat_id,
                            "caption": caption,
                            "parse_mode": "Markdown",
                            "reply_markup": json.dumps(reply_markup),
                        }
                        resp = client.post(url, data=data, files=files)
                else:
                    url = f"{self.base_url}/sendMessage"
                    payload = {
                        "chat_id": self.config.chat_id,
                        "text": caption,
                        "parse_mode": "Markdown",
                        "reply_markup": reply_markup,
                    }
                    resp = client.post(url, json=payload)

                if resp.status_code == 200:
                    msg_id = resp.json().get("result", {}).get("message_id")
                    logger.info(f"Sent Telegram signal alert (message_id: {msg_id})")
                    return msg_id
                else:
                    logger.error(f"Telegram send failed ({resp.status_code}): {resp.text}")
                    return None
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return None

    def send_daily_plan(self, plan: DailyPlan, image_path: Optional[Path]) -> None:
        """Sends the Daily Plan to Telegram with the dual-screen overview formatted per content.md."""
        if not self.is_configured:
            return

        from src.planner.daily_planner import DailyPlanner
        caption = DailyPlanner.format_plan_message(plan)

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🔄 Cập nhật lại Plan", "callback_data": "trigger_plan"},
                ]
            ]
        }

        self._send_media_or_text(caption, image_path, reply_markup)

    def send_orderflow_trade_request(
        self,
        eval_result: OrderFlowTriggerEvaluation,
        trade_params: Optional[TradeParameters],
        image_path: Optional[Path],
        cycle_id: str,
        symbol: str,
    ) -> Optional[int]:
        """Sends the Trade Entry Proposal based on Plan Alignment + Footprint/Bookmap trigger."""
        if not self.is_configured or self.is_paused:
            return None

        dir_icon = "🟢 BUY" if eval_result.direction == "BUY" else "🔴 SELL"
        lines = [
            f"🚨 **YÊU CẦU VÀO LỆNH — {symbol} ({dir_icon})**",
            "⚠️ *Gửi trước khi nến đóng 15 giây (T-15s)*",
            "",
            f"📋 **Kịch bản khớp:** `{eval_result.matched_scenario or 'Plan Setup'}`",
            f"🎯 **Vùng kiểm tra:** {eval_result.zone_description}",
            f"⚡ **Tín hiệu Trigger:** {eval_result.trigger_description}",
            "",
        ]

        if trade_params:
            tp = trade_params
            lines.extend([
                f"📊 **Thông số lệnh đề xuất (Fixed Risk $250):**",
                f"• Entry: `{tp.entry_price:.2f}`",
                f"• Stop Loss: `{tp.stop_loss:.2f}` ({tp.sl_points:.1f} pts)",
                f"• Take Profit: `{tp.take_profit:.2f}` (R:R = 1:{tp.risk_reward_ratio:.1f})",
                f"• Khối lượng đề xuất: `{tp.lot_size:.2f} lot`",
                "",
            ])

        lines.append(f"💡 *Đánh giá Order Flow:* {eval_result.summary}")
        lines.append(f"\n_Mã chu kỳ: {cycle_id}_")
        caption = "\n".join(lines)

        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ DUYỆT VÀO LỆNH (Approve)",
                        "callback_data": f"label:{cycle_id}:VALID",
                    },
                    {
                        "text": "❌ BỎ QUA (Reject)",
                        "callback_data": f"label:{cycle_id}:INVALID",
                    },
                ]
            ]
        }

        return self._send_media_or_text(caption, image_path, reply_markup)

    def _send_media_or_text(
        self, text: str, image_path: Optional[Path], reply_markup: Optional[dict] = None
    ) -> Optional[int]:
        try:
            with httpx.Client(timeout=20.0) as client:
                # 1. If image is provided and exists
                if image_path and image_path.exists():
                    url_photo = f"{self.base_url}/sendPhoto"
                    
                    if len(text) <= 1024:
                        with open(image_path, "rb") as photo_file:
                            data = {
                                "chat_id": self.config.chat_id,
                                "caption": text,
                                "parse_mode": "Markdown",
                            }
                            if reply_markup:
                                data["reply_markup"] = json.dumps(reply_markup)
                            resp = client.post(url_photo, data=data, files={"photo": photo_file})
                        
                        if resp.status_code == 200:
                            return resp.json().get("result", {}).get("message_id")
                        else:
                            # Fallback without parse_mode
                            with open(image_path, "rb") as photo_file:
                                data = {"chat_id": self.config.chat_id, "caption": text}
                                if reply_markup:
                                    data["reply_markup"] = json.dumps(reply_markup)
                                resp2 = client.post(url_photo, data=data, files={"photo": photo_file})
                            if resp2.status_code == 200:
                                return resp2.json().get("result", {}).get("message_id")
                    else:
                        # Caption exceeds Telegram 1024 limit: send photo with short title first
                        with open(image_path, "rb") as photo_file:
                            data = {
                                "chat_id": self.config.chat_id,
                                "caption": "📊 **Order Flow Overview (VP, Footprint, Bookmap)**",
                                "parse_mode": "Markdown",
                            }
                            client.post(url_photo, data=data, files={"photo": photo_file})

                # 2. Send text message (supports up to 4096 chars)
                url_msg = f"{self.base_url}/sendMessage"
                payload = {
                    "chat_id": self.config.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                resp = client.post(url_msg, json=payload)

                if resp.status_code == 200:
                    return resp.json().get("result", {}).get("message_id")
                else:
                    # Retry without Markdown formatting if parsing error
                    payload.pop("parse_mode", None)
                    resp2 = client.post(url_msg, json=payload)
                    if resp2.status_code == 200:
                        return resp2.json().get("result", {}).get("message_id")
                    logger.error(f"Telegram API error {resp2.status_code}: {resp2.text}")
                    return None
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return None

    def send_recheck_outcome(
        self,
        decision: SignalDecision,
        recheck: RecheckResult,
        symbol: str,
    ) -> None:
        """FR-11: Sends immediate notification if invalidated or confirmed after candle close."""
        if not self.is_configured:
            return

        if recheck.status_label == "INVALIDATED":
            text = (
                f"🛑 **SIGNAL INVALIDATED AT CANDLE CLOSE**\n"
                f"Symbol: `{symbol}` | Bias: `{decision.direction}`\n\n"
                f"⚠️ *Reason:* {recheck.reason}\n"
                f"Do NOT execute this trade.\n"
                f"_Cycle ID: {decision.cycle_id}_"
            )
        elif recheck.status_label == "CONFIRMED":
            text = (
                f"✅ **CONFIRMED AFTER CANDLE CLOSE**\n"
                f"Symbol: `{symbol}` | Bias: `{decision.direction}`\n"
                f"Candle closed in alignment: {recheck.reason}\n"
                f"_Cycle ID: {decision.cycle_id}_"
            )
        else:
            text = (
                f"⚠️ **CONFIRMATION WARNING**\n"
                f"Symbol: `{symbol}`: {recheck.reason}"
            )

        self.send_text(text)

    def send_system_alert(self, message: str) -> None:
        """Sends operational or error alerts (ST-007 AC-2)."""
        if not self.is_configured:
            return
        text = f"⚙️ **SYSTEM ALERT**\n{message}"
        self.send_text(text)

    def send_text(self, text: str, reply_markup: Optional[dict] = None) -> None:
        try:
            with httpx.Client(timeout=10.0) as client:
                url = f"{self.base_url}/sendMessage"
                payload = {
                    "chat_id": self.config.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                client.post(url, json=payload)
        except Exception as e:
            logger.error(f"Failed to send Telegram text: {e}")

    def process_updates(self) -> None:
        """
        Polls for commands (/pause, /resume, /stats) and button callbacks (✅ / ❌).
        """
        if not self.is_configured:
            return

        url = f"{self.base_url}/getUpdates"
        params = {"offset": self._last_update_id + 1, "timeout": 2}

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    return

                updates = resp.json().get("result", [])
                for update in updates:
                    self._last_update_id = update["update_id"]

                    # Handle Callback Queries (Button clicks: ✅ / ❌)
                    if "callback_query" in update:
                        cb = update["callback_query"]
                        cb_id = cb["id"]
                        data = cb.get("data", "")
                        if data.startswith("label:"):
                            parts = data.split(":")
                            if len(parts) == 3:
                                _, cycle_id, label = parts
                                self.storage.record_feedback(cycle_id, label)
                                label_emoji = "✅ Validated" if label == "VALID" else "❌ Marked Invalid"
                                client.post(
                                    f"{self.base_url}/answerCallbackQuery",
                                    json={"callback_query_id": cb_id, "text": f"Saved: {label_emoji}"},
                                )
                                self.send_text(f"📝 Cycle `{cycle_id}` was labeled {label_emoji} by trader.")
                        elif data == "trigger_plan":
                            client.post(
                                f"{self.base_url}/answerCallbackQuery",
                                json={"callback_query_id": cb_id, "text": "Đang khởi tạo Daily Plan..."},
                            )
                            if self.on_plan_requested:
                                self.on_plan_requested()

                    # Handle Chat Commands
                    if "message" in update and "text" in update["message"]:
                        text = update["message"]["text"].strip().lower()

                        if text in ("/start", "/help"):
                            reply_markup = {
                                "inline_keyboard": [
                                    [{"text": "🔄 Cập nhật lại Plan", "callback_data": "trigger_plan"}]
                                ]
                            }
                            self.send_text(
                                "👋 Xin chào! Hệ thống Bot phân tích Order Flow đang trực tuyến.\n\n"
                                "Bấm nút **[🔄 Cập nhật lại Plan]** bên dưới để kích hoạt chụp 2 màn hình và phân tích kế hoạch mới nhất.",
                                reply_markup=reply_markup,
                            )
                        elif text == "/pause":
                            self.is_paused = True
                            self.send_text("⏸️ Trading Agent is now **PAUSED**. Signals suppressed.")
                        elif text == "/resume":
                            self.is_paused = False
                            self.send_text("▶️ Trading Agent has **RESUMED**.")
                        elif text == "/plan":
                            self.send_text("🔄 Đang chụp 2 màn hình (VP/Footprint & Bookmap) và phân tích Daily Plan...")
                            if self.on_plan_requested:
                                self.on_plan_requested()
                        elif text == "/stats":
                            stats = self.storage.get_stats()
                            msg = (
                                f"📊 **Performance & Accuracy Stats:**\n"
                                f"• Total READY Signals: {stats['total_ready']}\n"
                                f"• Valid (✅): {stats['valid_count']}\n"
                                f"• Invalid (❌): {stats['invalid_count']}\n"
                                f"• Unlabeled: {stats['unlabeled_count']}\n"
                                f"• Precision / Accuracy: **{stats['accuracy_pct']}%**"
                            )
                            self.send_text(msg)
                        elif text == "/status":
                            status_str = "PAUSED" if self.is_paused else "ACTIVE"
                            self.send_text(f"ℹ️ Status: `{status_str}`")
        except Exception as e:
            logger.debug(f"Update polling error: {e}")

