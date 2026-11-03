import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.decision.models import SignalDecision

logger = logging.getLogger(__name__)


class CycleStorage:
    def __init__(self, db_path: str = "data/trading_agent.db", jsonl_path: str = "data/cycles.jsonl"):
        self.db_path = Path(db_path)
        self.jsonl_path = Path(jsonl_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cycles (
                    cycle_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    state TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    image_path TEXT,
                    analysis_json TEXT,
                    trade_params_json TEXT,
                    decision_reasons TEXT,
                    recheck_status TEXT,
                    telegram_message_id INTEGER,
                    feedback_label TEXT,
                    feedback_timestamp TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cycles_state ON cycles(state);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cycles_timestamp ON cycles(timestamp);
            """)
            conn.commit()

    def record_cycle(
        self,
        decision: SignalDecision,
        symbol: str,
        image_path: Optional[str] = None,
        telegram_message_id: Optional[int] = None,
        recheck_status: Optional[str] = None,
    ) -> None:
        """Saves cycle record to both SQLite and JSONL."""
        timestamp_str = decision.timestamp.isoformat()
        analysis_json_str = (
            decision.analysis.model_dump_json() if decision.analysis else "{}"
        )
        trade_params_json_str = (
            decision.trade_params.model_dump_json() if decision.trade_params else "{}"
        )
        reasons_str = json.dumps(decision.reasons)

        # 1. SQLite record
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO cycles (
                    cycle_id, timestamp, symbol, state, direction,
                    image_path, analysis_json, trade_params_json,
                    decision_reasons, recheck_status, telegram_message_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.cycle_id,
                    timestamp_str,
                    symbol,
                    decision.state.value,
                    decision.direction,
                    str(image_path) if image_path else "",
                    analysis_json_str,
                    trade_params_json_str,
                    reasons_str,
                    recheck_status,
                    telegram_message_id,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

        # 2. JSONL record (ST-007 AC-1)
        jsonl_entry = {
            "cycle_id": decision.cycle_id,
            "timestamp": timestamp_str,
            "symbol": symbol,
            "state": decision.state.value,
            "direction": decision.direction,
            "image_path": str(image_path) if image_path else "",
            "analysis": decision.analysis.model_dump() if decision.analysis else None,
            "trade_params": decision.trade_params.model_dump() if decision.trade_params else None,
            "reasons": decision.reasons,
            "recheck_status": recheck_status,
            "telegram_message_id": telegram_message_id,
        }

        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(jsonl_entry) + "\n")

    def update_recheck_status(self, cycle_id: str, recheck_status: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE cycles SET recheck_status = ? WHERE cycle_id = ?",
                (recheck_status, cycle_id),
            )
            conn.commit()

    def record_feedback(self, cycle_id: str, label: str) -> bool:
        """ST-006 AC-1: Saves label (✅ or ❌) for a given cycle."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE cycles
                SET feedback_label = ?, feedback_timestamp = ?
                WHERE cycle_id = ?
                """,
                (label, datetime.now().isoformat(), cycle_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_stats(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """ST-006 AC-2: Aggregates total signals, labels, and accuracy."""
        query = "SELECT state, feedback_label FROM cycles WHERE state = 'READY'"
        params = []
        if date_str:
            query += " AND date(timestamp) = date(?)"
            params.append(date_str)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        total_ready = len(rows)
        valid_count = sum(1 for r in rows if r[1] == "VALID")
        invalid_count = sum(1 for r in rows if r[1] == "INVALID")
        unlabeled_count = sum(1 for r in rows if r[1] is None)

        labeled_total = valid_count + invalid_count
        accuracy_pct = (valid_count / labeled_total * 100.0) if labeled_total > 0 else 0.0

        return {
            "total_ready": total_ready,
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "unlabeled_count": unlabeled_count,
            "accuracy_pct": round(accuracy_pct, 1),
        }

    def check_heartbeat(self, max_idle_minutes: int = 15) -> bool:
        """
        ST-007 AC-2: Checks if a successful cycle occurred in the last max_idle_minutes.
        Returns False if idle exceeded.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT timestamp FROM cycles ORDER BY timestamp DESC LIMIT 1"
            )
            row = cursor.fetchone()

        if not row:
            return True  # No cycles yet

        last_time = datetime.fromisoformat(row[0])
        if datetime.now() - last_time > timedelta(minutes=max_idle_minutes):
            return False
        return True

