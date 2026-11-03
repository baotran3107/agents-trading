import logging
from typing import Optional, Tuple
from pydantic import BaseModel
from src.decision.models import SignalDecision
from src.mt5.client import BaseMT5Client, MT5ConnectionError
from src.mt5.models import CandleData, RawPrices

logger = logging.getLogger(__name__)


class RecheckResult(BaseModel):
    is_valid: bool
    status_label: str  # "CONFIRMED" or "INVALIDATED"
    reason: str
    closed_candle: Optional[CandleData] = None
    raw_prices: Optional[RawPrices] = None


class CandleCloseVerifier:
    """
    ST-008 & FR-11:
    Re-checks signals when the candle officially closes using raw MT5 numerical data.
    """

    def __init__(self, mt5_client: BaseMT5Client):
        self.mt5_client = mt5_client

    def verify_at_candle_close(
        self,
        decision: SignalDecision,
        symbol: str,
        timeframe_minutes: int = 5,
    ) -> RecheckResult:
        try:
            raw_prices = self.mt5_client.get_raw_prices(symbol)
            closed_candle = self.mt5_client.get_closed_candle(symbol, timeframe_minutes)
        except MT5ConnectionError as e:
            logger.error(f"ST-008 AC-4: MT5 lost connection at candle close: {e}")
            return RecheckResult(
                is_valid=False,
                status_label="UNCONFIRMED_CONNECTION_LOST",
                reason=f"Could not verify after candle close: MT5 connection lost ({e}).",
            )

        if not decision.trade_params:
            return RecheckResult(
                is_valid=True,
                status_label="CONFIRMED",
                reason="No numerical parameters to verify.",
                closed_candle=closed_candle,
                raw_prices=raw_prices,
            )

        direction = decision.direction
        sl = decision.trade_params.stop_loss
        close_p = closed_candle.close
        open_p = closed_candle.open

        # Numerical Rule 1: Stop Loss breach check
        if direction == "BUY" and close_p <= sl:
            return RecheckResult(
                is_valid=False,
                status_label="INVALIDATED",
                reason=f"Candle closed at {close_p:.2f}, breaching Stop Loss ({sl:.2f}).",
                closed_candle=closed_candle,
                raw_prices=raw_prices,
            )
        elif direction == "SELL" and close_p >= sl:
            return RecheckResult(
                is_valid=False,
                status_label="INVALIDATED",
                reason=f"Candle closed at {close_p:.2f}, breaching Stop Loss ({sl:.2f}).",
                closed_candle=closed_candle,
                raw_prices=raw_prices,
            )

        # Numerical Rule 2: Directional candle confirmation
        # A BUY trigger candle should not close as a heavy opposing bearish candle
        if direction == "BUY" and close_p < open_p:
            # Bearish close on supposed bullish trigger
            bearish_distance = open_p - close_p
            candle_range = closed_candle.high - closed_candle.low
            if candle_range > 0 and (bearish_distance / candle_range) > 0.5:
                return RecheckResult(
                    is_valid=False,
                    status_label="INVALIDATED",
                    reason=(
                        f"Candle closed bearish ({open_p:.2f} -> {close_p:.2f}), "
                        "invalidating bullish rejection."
                    ),
                    closed_candle=closed_candle,
                    raw_prices=raw_prices,
                )

        if direction == "SELL" and close_p > open_p:
            # Bullish close on supposed bearish trigger
            bullish_distance = close_p - open_p
            candle_range = closed_candle.high - closed_candle.low
            if candle_range > 0 and (bullish_distance / candle_range) > 0.5:
                return RecheckResult(
                    is_valid=False,
                    status_label="INVALIDATED",
                    reason=(
                        f"Candle closed bullish ({open_p:.2f} -> {close_p:.2f}), "
                        "invalidating bearish rejection."
                    ),
                    closed_candle=closed_candle,
                    raw_prices=raw_prices,
                )

        return RecheckResult(
            is_valid=True,
            status_label="CONFIRMED",
            reason=f"Confirmed after candle close (Closed at {close_p:.2f}).",
            closed_candle=closed_candle,
            raw_prices=raw_prices,
        )

