import logging
from typing import Optional
from src.config import RiskConfig
from src.decision.models import TradeParameters
from src.mt5.models import RawPrices

logger = logging.getLogger(__name__)


class RiskCalculator:
    def __init__(self, config: RiskConfig):
        self.config = config

    def calculate_trade_parameters(
        self,
        direction: str,
        raw_prices: RawPrices,
    ) -> Optional[TradeParameters]:
        """
        Calculates Entry, SL, TP, and Lot size for fixed USD risk ($250).
        SL is derived strictly from 15-minute high/low (FR-6).
        """
        if direction not in ("BUY", "SELL"):
            return None

        entry = raw_prices.current_price

        if direction == "BUY":
            sl = raw_prices.m15_low
            if sl >= entry:
                # Fallback safeguard if current price dipped below low
                sl = entry - self.config.min_sl_points
            sl_points = entry - sl
            tp = entry + (sl_points * self.config.risk_reward_ratio)

        elif direction == "SELL":
            sl = raw_prices.m15_high
            if sl <= entry:
                # Fallback safeguard if current price rose above high
                sl = entry + self.config.min_sl_points
            sl_points = sl - entry
            tp = entry - (sl_points * self.config.risk_reward_ratio)

        # Enforce SL limits
        if sl_points < self.config.min_sl_points:
            sl_points = self.config.min_sl_points
            sl = (entry - sl_points) if direction == "BUY" else (entry + sl_points)
            tp = entry + (sl_points * self.config.risk_reward_ratio) if direction == "BUY" else entry - (sl_points * self.config.risk_reward_ratio)

        # Calculate lot size: fixed_loss / (sl_points * point_value)
        # For XAUUSD, 1 point ($1 move on 1 lot) = $100 for 100oz contract, or configured
        cost_per_point_per_lot = self.config.point_value_per_lot
        raw_lot = self.config.fixed_loss_usd / (sl_points * cost_per_point_per_lot)
        lot_size = max(0.01, round(raw_lot, 2))

        return TradeParameters(
            entry_price=round(entry, 2),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            sl_points=round(sl_points, 2),
            risk_reward_ratio=self.config.risk_reward_ratio,
            lot_size=lot_size,
            fixed_loss_usd=self.config.fixed_loss_usd,
        )

