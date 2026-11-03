import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional
import httpx
from src.config import TelegramConfig
from src.decision.models import AgentState, SignalDecision
from src.decision.recheck import RecheckResult
from src.storage.logger import CycleStorage

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, config: TelegramConfig, storage: CycleStorage):
        self.config = config
        self.storage = storage
        self.base_url = f"https://api.telegram.org/bot{self.config.bot_token}"
        self.is_paused = False
        self._last_update_id = 0

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
                            "reply_markup": httpx._compat.json_dumps(reply_markup),
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

    def send_text(self, text: str) -> None:
        try:
            with httpx.Client(timeout=10.0) as client:
                url = f"{self.base_url}/sendMessage"
                payload = {
                    "chat_id": self.config.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                }
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

                    # Handle Chat Commands
                    if "message" in update and "text" in update["message"]:
                        text = update["message"]["text"].strip().lower()

                        if text == "/pause":
                            self.is_paused = True
                            self.send_text("⏸️ Trading Agent is now **PAUSED**. Signals suppressed.")
                        elif text == "/resume":
                            self.is_paused = False
                            self.send_text("▶️ Trading Agent has **RESUMED**.")
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

