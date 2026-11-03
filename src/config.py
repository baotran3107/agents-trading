import os
from pathlib import Path
from typing import Optional
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class ActiveHoursConfig(BaseModel):
    enabled: bool = True
    start: str = "08:00"
    end: str = "22:00"
    timezone: str = "UTC"


class TradingConfig(BaseModel):
    symbol: str = "XAUUSD"
    timeframe_minutes: int = 5
    t_minus_seconds: int = 10
    active_hours: ActiveHoursConfig = Field(default_factory=ActiveHoursConfig)


class RiskConfig(BaseModel):
    fixed_loss_usd: float = 250.0
    risk_reward_ratio: float = 2.0
    min_sl_points: float = 10.0
    max_sl_points: float = 500.0
    point_value_per_lot: float = 1.0


class ModelConfig(BaseModel):
    provider: str = "cli"  # "cli" or "gemini_api"
    cli_path: str = "agy"
    model_name: str = "gemini-4-argon-medium"
    api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY")
    )
    timeout_seconds: int = 35
    retry_attempts: int = 1


class TelegramConfig(BaseModel):
    enabled: bool = True
    bot_token: str = Field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    chat_id: str = Field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    cooldown_minutes: int = 15
    send_watch_signals: bool = True
    send_ready_signals: bool = True


class CaptureConfig(BaseModel):
    window_title: str = "MetaTrader 5"
    black_threshold: float = 5.0
    output_dir: str = "data/captures"


class MT5Config(BaseModel):
    mode: str = "auto"
    login: Optional[int] = Field(
        default_factory=lambda: int(os.getenv("MT5_LOGIN")) if os.getenv("MT5_LOGIN") else None
    )
    password: Optional[str] = Field(default_factory=lambda: os.getenv("MT5_PASSWORD"))
    server: Optional[str] = Field(default_factory=lambda: os.getenv("MT5_SERVER"))
    path: Optional[str] = Field(default_factory=lambda: os.getenv("MT5_PATH"))


class StorageConfig(BaseModel):
    db_path: str = "data/trading_agent.db"
    log_file: str = "data/cycles.jsonl"
    heartbeat_timeout_minutes: int = 15


class AppConfig(BaseModel):
    trading: TradingConfig = Field(default_factory=TradingConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    mt5: MT5Config = Field(default_factory=MT5Config)
    storage: StorageConfig = Field(default_factory=StorageConfig)


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    if config_path is None:
        config_path = BASE_DIR / "config" / "config.yaml"

    config_data = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

    return AppConfig(**config_data)
