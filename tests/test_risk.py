from datetime import datetime
import pytest
from src.config import RiskConfig
from src.decision.risk import RiskCalculator
from src.mt5.models import RawPrices


def test_calculate_trade_parameters_buy():
    cfg = RiskConfig(
        fixed_loss_usd=250.0,
        risk_reward_ratio=2.0,
        min_sl_points=10.0,
        point_value_per_lot=1.0,
    )
    calc = RiskCalculator(cfg)

    prices = RawPrices(
        symbol="XAUUSD",
        timestamp=datetime.now(),
        bid=2700.0,
        ask=2700.2,
        current_price=2700.0,
        m15_high=2710.0,
        m15_low=2680.0,
    )

    params = calc.calculate_trade_parameters("BUY", prices)
    assert params is not None
    assert params.entry_price == 2700.0
    assert params.stop_loss == 2680.0
    assert params.sl_points == 20.0
    # TP = Entry + (20 * 2) = 2740.0
    assert params.take_profit == 2740.0
    # Lot = 250 / (20 * 1.0) = 12.5
    assert params.lot_size == 12.5


def test_calculate_trade_parameters_sell():
    cfg = RiskConfig(
        fixed_loss_usd=250.0,
        risk_reward_ratio=2.0,
        min_sl_points=5.0,
        point_value_per_lot=1.0,
    )
    calc = RiskCalculator(cfg)

    prices = RawPrices(
        symbol="XAUUSD",
        timestamp=datetime.now(),
        bid=2700.0,
        ask=2700.2,
        current_price=2700.0,
        m15_high=2725.0,
        m15_low=2680.0,
    )

    params = calc.calculate_trade_parameters("SELL", prices)
    assert params is not None
    assert params.entry_price == 2700.0
    assert params.stop_loss == 2725.0
    assert params.sl_points == 25.0
    # TP = Entry - (25 * 2) = 2650.0
    assert params.take_profit == 2650.0
    # Lot = 250 / (25 * 1.0) = 10.0
    assert params.lot_size == 10.0


def test_calculate_orderflow_parameters():
    cfg = RiskConfig(
        fixed_loss_usd=250.0,
        risk_reward_ratio=2.0,
        min_sl_points=5.0,
        point_value_per_lot=1.0,
    )
    calc = RiskCalculator(cfg)

    # Directly from chart screen analysis (without MT5 raw prices)
    params = calc.calculate_orderflow_parameters(
        direction="BUY",
        entry=2696.50,
        sl=2694.00,
        tp=2701.50,
    )
    assert params is not None
    assert params.entry_price == 2696.50
    # sl_points was 2.5 (< min_sl_points 5.0), so adjusted to 5.0 and sl = 2696.5 - 5.0 = 2691.50
    assert params.sl_points == 5.0
    assert params.stop_loss == 2691.50
    assert params.lot_size == 50.0  # 250 / (5.0 * 1.0)

