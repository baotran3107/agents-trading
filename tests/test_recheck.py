from datetime import datetime
import pytest
from src.decision.models import AgentState, SignalDecision, TradeParameters
from src.decision.recheck import CandleCloseVerifier
from src.mt5.client import MockMT5Client
from src.mt5.models import CandleData, RawPrices


class StubMT5Client(MockMT5Client):
    def __init__(self, closed_candle: CandleData, raw_prices: RawPrices, simulate_disconnect=False):
        super().__init__(simulate_disconnect=simulate_disconnect)
        self.stub_candle = closed_candle
        self.stub_prices = raw_prices

    def get_closed_candle(self, symbol: str, timeframe_minutes: int = 5) -> CandleData:
        if not self.is_connected():
            from src.mt5.client import MT5ConnectionError
            raise MT5ConnectionError("MT5 disconnected")
        return self.stub_candle

    def get_raw_prices(self, symbol: str) -> RawPrices:
        if not self.is_connected():
            from src.mt5.client import MT5ConnectionError
            raise MT5ConnectionError("MT5 disconnected")
        return self.stub_prices


def test_recheck_confirmed():
    now = datetime.now()
    trade_params = TradeParameters(
        entry_price=2700.0,
        stop_loss=2690.0,
        take_profit=2720.0,
        sl_points=10.0,
        risk_reward_ratio=2.0,
        lot_size=2.5,
        fixed_loss_usd=250.0,
    )
    decision = SignalDecision(
        cycle_id="c1",
        timestamp=now,
        state=AgentState.READY,
        direction="BUY",
        analysis=None,
        trade_params=trade_params,
    )

    candle = CandleData(time=now, open=2698.0, high=2704.0, low=2697.0, close=2702.0)
    prices = RawPrices(symbol="XAUUSD", timestamp=now, bid=2702, ask=2702.2, current_price=2702, m15_high=2720, m15_low=2690)
    client = StubMT5Client(candle, prices)

    verifier = CandleCloseVerifier(client)
    result = verifier.verify_at_candle_close(decision, "XAUUSD")

    assert result.is_valid is True
    assert result.status_label == "CONFIRMED"


def test_recheck_invalidated_by_sl_breach():
    now = datetime.now()
    trade_params = TradeParameters(
        entry_price=2700.0,
        stop_loss=2690.0,
        take_profit=2720.0,
        sl_points=10.0,
        risk_reward_ratio=2.0,
        lot_size=2.5,
        fixed_loss_usd=250.0,
    )
    decision = SignalDecision(
        cycle_id="c2",
        timestamp=now,
        state=AgentState.READY,
        direction="BUY",
        analysis=None,
        trade_params=trade_params,
    )

    # Candle closed below SL (2688.0 <= 2690.0)
    candle = CandleData(time=now, open=2698.0, high=2700.0, low=2687.0, close=2688.0)
    prices = RawPrices(symbol="XAUUSD", timestamp=now, bid=2688, ask=2688.2, current_price=2688, m15_high=2720, m15_low=2685)
    client = StubMT5Client(candle, prices)

    verifier = CandleCloseVerifier(client)
    result = verifier.verify_at_candle_close(decision, "XAUUSD")

    assert result.is_valid is False
    assert result.status_label == "INVALIDATED"
    assert "breaching Stop Loss" in result.reason

