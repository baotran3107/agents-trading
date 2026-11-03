import logging
import platform
import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional
from src.config import MT5Config
from src.mt5.models import CandleData, RawPrices

logger = logging.getLogger(__name__)


class MT5ConnectionError(Exception):
    """Raised when connection to MT5 is lost or cannot be established."""
    pass


class BaseMT5Client(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def get_raw_prices(self, symbol: str) -> RawPrices:
        pass

    @abstractmethod
    def get_closed_candle(self, symbol: str, timeframe_minutes: int = 5) -> CandleData:
        pass


class NativeMT5Client(BaseMT5Client):
    """Client for Windows MT5 using the official MetaTrader5 Python package."""

    def __init__(self, config: MT5Config):
        self.config = config
        self._mt5 = None

    def connect(self) -> bool:
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
        except ImportError:
            raise MT5ConnectionError("MetaTrader5 package is not installed (Windows only).")

        init_args = {}
        if self.config.path:
            init_args["path"] = self.config.path
        if self.config.login:
            init_args["login"] = self.config.login
        if self.config.password:
            init_args["password"] = self.config.password
        if self.config.server:
            init_args["server"] = self.config.server

        if not self._mt5.initialize(**init_args):
            err = self._mt5.last_error()
            logger.error(f"MT5 initialization failed: {err}")
            raise MT5ConnectionError(f"MT5 initialization failed: {err}")

        terminal_info = self._mt5.terminal_info()
        if not terminal_info or not terminal_info.connected:
            raise MT5ConnectionError("MT5 terminal is not connected to broker.")

        logger.info("Successfully connected to native MetaTrader 5.")
        return True

    def disconnect(self) -> None:
        if self._mt5:
            self._mt5.shutdown()

    def is_connected(self) -> bool:
        if not self._mt5:
            return False
        info = self._mt5.terminal_info()
        return bool(info and info.connected)

    def get_raw_prices(self, symbol: str) -> RawPrices:
        if not self.is_connected():
            raise MT5ConnectionError("MT5 connection is lost (ST-003 AC-2).")

        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5ConnectionError(f"Failed to fetch tick for symbol: {symbol}")

        # Fetch recent 15-minute rates to calculate M15 high/low
        # TIMEFRAME_M15 = 15 in MT5
        rates_m15 = self._mt5.copy_rates_from_pos(symbol, self._mt5.TIMEFRAME_M15, 0, 5)
        if rates_m15 is None or len(rates_m15) == 0:
            raise MT5ConnectionError(f"Failed to fetch M15 rates for symbol: {symbol}")

        # Use the most recent completed M15 candles for high/low
        m15_high = float(max(r['high'] for r in rates_m15))
        m15_low = float(min(r['low'] for r in rates_m15))
        current_price = (tick.bid + tick.ask) / 2.0

        return RawPrices(
            symbol=symbol,
            timestamp=datetime.now(),
            bid=float(tick.bid),
            ask=float(tick.ask),
            current_price=current_price,
            m15_high=m15_high,
            m15_low=m15_low,
        )

    def get_closed_candle(self, symbol: str, timeframe_minutes: int = 5) -> CandleData:
        if not self.is_connected():
            raise MT5ConnectionError("MT5 connection is lost.")

        tf_map = {1: self._mt5.TIMEFRAME_M1, 5: self._mt5.TIMEFRAME_M5, 15: self._mt5.TIMEFRAME_M15}
        tf = tf_map.get(timeframe_minutes, self._mt5.TIMEFRAME_M5)

        # Index 1 is the last fully completed candle
        rates = self._mt5.copy_rates_from_pos(symbol, tf, 1, 1)
        if rates is None or len(rates) == 0:
            raise MT5ConnectionError("Failed to fetch closed candle.")

        bar = rates[0]
        return CandleData(
            time=datetime.fromtimestamp(bar['time']),
            open=float(bar['open']),
            high=float(bar['high']),
            low=float(bar['low']),
            close=float(bar['close']),
            tick_volume=int(bar['tick_volume']),
        )


class MockMT5Client(BaseMT5Client):
    """
    Mock MT5 Client for local testing, macOS development, and CI.
    Generates realistic prices and simulates disconnection if requested.
    """

    def __init__(self, base_price: float = 2700.0, simulate_disconnect: bool = False):
        self.base_price = base_price
        self._connected = True
        self.simulate_disconnect = simulate_disconnect

    def connect(self) -> bool:
        if self.simulate_disconnect:
            raise MT5ConnectionError("Simulated connection failure.")
        self._connected = True
        logger.info("Connected to Mock MT5 Client.")
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected and not self.simulate_disconnect

    def set_connected(self, status: bool) -> None:
        self._connected = status

    def get_raw_prices(self, symbol: str) -> RawPrices:
        if not self.is_connected():
            raise MT5ConnectionError("MT5 connection lost (Mock).")

        delta = random.uniform(-0.5, 0.5)
        price = self.base_price + delta
        spread = 0.20
        bid = price - spread / 2
        ask = price + spread / 2

        m15_high = price + random.uniform(2.0, 5.0)
        m15_low = price - random.uniform(2.0, 5.0)

        return RawPrices(
            symbol=symbol,
            timestamp=datetime.now(),
            bid=round(bid, 2),
            ask=round(ask, 2),
            current_price=round(price, 2),
            m15_high=round(m15_high, 2),
            m15_low=round(m15_low, 2),
        )

    def get_closed_candle(self, symbol: str, timeframe_minutes: int = 5) -> CandleData:
        if not self.is_connected():
            raise MT5ConnectionError("MT5 connection lost (Mock).")

        open_p = self.base_price
        close_p = self.base_price + random.uniform(-1.5, 1.5)
        high_p = max(open_p, close_p) + random.uniform(0.1, 1.0)
        low_p = min(open_p, close_p) - random.uniform(0.1, 1.0)

        return CandleData(
            time=datetime.now() - timedelta(minutes=timeframe_minutes),
            open=round(open_p, 2),
            high=round(high_p, 2),
            low=round(low_p, 2),
            close=round(close_p, 2),
            tick_volume=120,
        )


def get_mt5_client(config: MT5Config) -> BaseMT5Client:
    """Factory creating appropriate client based on OS and config."""
    if config.mode == "mock":
        return MockMT5Client()

    if config.mode == "native":
        return NativeMT5Client(config)

    # Auto mode: if on Windows, attempt Native, else Mock
    if platform.system() == "Windows":
        try:
            return NativeMT5Client(config)
        except Exception as e:
            logger.warning(f"Failed to load native MT5 client: {e}. Falling back to Mock.")
            return MockMT5Client()
    else:
        logger.info("Non-Windows OS detected: using Mock MT5 client.")
        return MockMT5Client()

