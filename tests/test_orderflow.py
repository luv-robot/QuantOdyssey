from datetime import datetime, timedelta

from app.models import (
    AggregateTrade,
    FailedBreakoutUniverseCell,
    FailedBreakoutUniverseReport,
    OhlcvCandle,
    StrategyFamily,
)
from app.services.harness import run_failed_breakout_orderflow_acceptance_validation
from app.services.market_data import build_orderflow_bars, collect_symbol_orderflow_once
from app.storage import QuantRepository


def test_build_orderflow_bars_tracks_taker_flow_and_cvd() -> None:
    trades = [
        _trade(1, buyer_is_maker=False, quantity=2, timestamp=datetime(2024, 1, 1, 0, 0, 5)),
        _trade(2, buyer_is_maker=True, quantity=1, timestamp=datetime(2024, 1, 1, 0, 0, 20)),
        _trade(3, buyer_is_maker=False, quantity=3, timestamp=datetime(2024, 1, 1, 0, 1, 5)),
    ]

    bars = build_orderflow_bars(trades, interval="1m")

    assert len(bars) == 2
    assert bars[0].buy_volume == 2
    assert bars[0].sell_volume == 1
    assert bars[0].net_taker_volume == 1
    assert bars[0].cumulative_volume_delta == 1
    assert bars[0].taker_buy_ratio == round(2 / 3, 8)
    assert bars[1].cumulative_volume_delta == 4


def test_repository_persists_aggregate_trades_and_orderflow_bars() -> None:
    repository = QuantRepository()
    trades = [_trade(1, buyer_is_maker=False)]
    bars = build_orderflow_bars(trades, interval="1m")

    repository.save_aggregate_trades("agg_dataset", "BTC/USDT:USDT", trades)
    repository.save_orderflow_bars("of_dataset", "BTC/USDT:USDT", bars)

    assert repository.get_aggregate_trades("agg_dataset") == trades
    assert repository.get_orderflow_bars("of_dataset") == bars
    assert repository.query_market_data_dataset_ids("orderflow_bar", symbol="BTC/USDT:USDT") == ["of_dataset"]


def test_collect_symbol_orderflow_once_uses_incremental_state() -> None:
    repository = QuantRepository()
    client = _FakeAggTradeClient(
        {
            None: [
                _trade(10, buyer_is_maker=False, quantity=2),
                _trade(11, buyer_is_maker=True, quantity=1),
            ],
            12: [_trade(12, buyer_is_maker=False, quantity=3)],
            13: [],
        }
    )
    state = {}

    result = collect_symbol_orderflow_once(
        symbol="BTC/USDT:USDT",
        trading_mode="futures",
        client=client,
        repository=repository,
        state=state,
        limit=2,
        max_pages=2,
        bar_interval="1m",
    )

    assert result["status"] == "saved"
    assert result["trade_count"] == 3
    assert state["futures:BTC/USDT:USDT"]["last_aggregate_trade_id"] == 12
    orderflow = repository.get_orderflow_bars(result["orderflow_dataset_id"])
    assert orderflow[-1].cumulative_volume_delta == 4

    second_result = collect_symbol_orderflow_once(
        symbol="BTC/USDT:USDT",
        trading_mode="futures",
        client=client,
        repository=repository,
        state=state,
        limit=2,
        max_pages=2,
        bar_interval="1m",
    )

    assert second_result["status"] == "no_new_trades"
    assert client.calls[-1] == 13


def test_failed_breakout_orderflow_acceptance_report_uses_taker_flow() -> None:
    universe = _universe_report()
    candles = _sample_candles()
    trades = []
    for event_index in (140, 360, 580):
        event_time = candles[event_index].open_time
        trades.append(_trade(event_index, buyer_is_maker=False, quantity=5, timestamp=event_time))
        trades.append(_trade(event_index + 1, buyer_is_maker=True, quantity=1, timestamp=event_time))
    orderflow = build_orderflow_bars(trades, interval="5m")

    report = run_failed_breakout_orderflow_acceptance_validation(
        universe_report=universe,
        candles_by_cell={("BTC/USDT:USDT", "5m"): candles},
        orderflow_by_cell={("BTC/USDT:USDT", "5m"): orderflow},
        horizon_hours=1,
        min_events_with_orderflow=1,
        min_confirmation_rate=0.5,
    )

    assert report.events_with_orderflow > 0
    assert report.confirms_failure_count > 0
    assert report.confirmation_rate > 0
    assert any("Orderflow" in item for item in report.findings)


def _trade(
    trade_id: int,
    *,
    buyer_is_maker: bool,
    quantity: float = 1,
    price: float = 100,
    timestamp: datetime | None = None,
) -> AggregateTrade:
    return AggregateTrade(
        symbol="BTC/USDT:USDT",
        aggregate_trade_id=trade_id,
        price=price,
        quantity=quantity,
        first_trade_id=trade_id,
        last_trade_id=trade_id,
        timestamp=timestamp or datetime(2024, 1, 1),
        buyer_is_maker=buyer_is_maker,
        raw={},
    )


class _FakeAggTradeClient:
    def __init__(self, responses: dict[int | None, list[AggregateTrade]]) -> None:
        self.responses = responses
        self.calls: list[int | None] = []

    def fetch_aggregate_trades(
        self,
        symbol: str,
        *,
        limit: int,
        trading_mode: str,
        from_id: int | None = None,
    ) -> list[AggregateTrade]:
        self.calls.append(from_id)
        return self.responses.get(from_id, [])[:limit]


def _universe_report() -> FailedBreakoutUniverseReport:
    trial_id = "trial_short_rolling_extreme_lb24_lq0_d10_aw3_af0_vz0"
    return FailedBreakoutUniverseReport(
        report_id="failed_breakout_universe_orderflow_test",
        thesis_id="thesis_failed_breakout",
        signal_id="signal_failed_breakout",
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        symbols=["BTC/USDT:USDT"],
        timeframes=["5m"],
        completed_cells=1,
        min_market_confirmations=1,
        robust_trial_ids=[trial_id],
        best_trial_frequency={trial_id: 1},
        cells=[
            FailedBreakoutUniverseCell(
                report_id="failed_breakout_btc_orderflow_test",
                symbol="BTC/USDT:USDT",
                timeframe="5m",
                completed_trials=1,
                robust_trial_count=1,
                simple_failed_breakout_total_return=-0.01,
                simple_failed_breakout_trade_count=6,
                best_trial_id=trial_id,
                best_trial_trade_count=6,
                best_trial_total_return=0.01,
                best_trial_profit_factor=1.2,
            )
        ],
    )


def _sample_candles(symbol: str = "BTC/USDT:USDT") -> list[OhlcvCandle]:
    start = datetime(2024, 1, 1)
    winning_events = {140, 360, 580}
    losing_events = {250, 470, 690}
    all_events = winning_events | losing_events
    candles: list[OhlcvCandle] = []
    for index in range(740):
        open_time = start + timedelta(minutes=5 * index)
        base = 100 + (index % 20) * 0.01
        close = base
        high = base + 0.3
        low = base - 0.3
        volume = 1000
        if index + 1 in all_events:
            high = 102.0
            close = 101.5
            volume = 1400
        if index in all_events:
            high = 101.8
            close = 100.1
            low = 99.9
            volume = 6000 if index in winning_events else 1000
        for event_index in winning_events:
            if event_index < index <= event_index + 12:
                close = 99.0 - (index - event_index) * 0.02
                high = max(high, close + 0.2)
                low = min(low, close - 0.2)
        for event_index in losing_events:
            if event_index < index <= event_index + 12:
                close = 101.0 + (index - event_index) * 0.02
                high = max(high, close + 0.2)
                low = min(low, close - 0.2)
        open_ = close + 0.03
        high = max(high, open_, close)
        low = min(low, open_, close)
        candles.append(
            OhlcvCandle(
                symbol=symbol,
                interval="5m",
                open_time=open_time,
                close_time=open_time + timedelta(minutes=5),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                quote_volume=volume * close,
                trade_count=100,
                raw=[],
            )
        )
    return candles
