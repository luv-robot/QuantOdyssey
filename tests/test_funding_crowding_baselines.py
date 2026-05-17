from datetime import datetime, timedelta, timezone

from app.models import (
    BacktestReport,
    BacktestStatus,
    FundingRatePoint,
    MarketSignal,
    OhlcvCandle,
    OpenInterestPoint,
    SignalType,
)
from app.services.backtester import compare_to_event_level_baselines, compare_to_proxy_baselines


def test_funding_signal_gets_type_specific_proxy_baselines() -> None:
    signal = MarketSignal(
        signal_id="signal_funding_baseline",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="5m",
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=88,
        features={"funding_percentile_30d": 94, "open_interest_percentile_30d": 82},
        hypothesis="funding crowding with failed breakout",
        data_sources=["ohlcv", "funding", "oi"],
    )
    backtest = BacktestReport(
        backtest_id="bt_funding",
        strategy_id="strategy_funding",
        timerange="20240101-20260501",
        trades=120,
        win_rate=0.58,
        profit_factor=1.6,
        sharpe=1.2,
        max_drawdown=-0.07,
        total_return=0.18,
        status=BacktestStatus.PASSED,
    )

    report = compare_to_proxy_baselines(signal, backtest)
    names = {item.name for item in report.baselines}

    assert "funding_extreme_only_proxy" in names
    assert "funding_plus_oi_proxy" in names
    assert "simple_failed_breakout_proxy" in names
    assert "opposite_direction_proxy" in names
    assert report.outperformed_best_baseline is True
    assert report.return_basis == "net_after_costs"
    assert report.cost_model.fee_rate > 0
    assert all(item.net_return == item.total_return for item in report.baselines)
    assert any((item.cost_drag or 0) > 0 for item in report.baselines)
    assert any("Funding-crowding baselines" in finding for finding in report.findings)
    assert any("net of configured" in finding for finding in report.findings)


def test_funding_signal_gets_event_level_baselines_when_market_data_is_available() -> None:
    signal = MarketSignal(
        signal_id="signal_funding_event_baseline",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=88,
        features={"funding_percentile_30d": 94, "open_interest_percentile_30d": 82},
        hypothesis="funding crowding with failed breakout",
        data_sources=["ohlcv", "funding"],
    )
    backtest = BacktestReport(
        backtest_id="bt_funding_event",
        strategy_id="strategy_funding_event",
        timerange="20240101-20260501",
        trades=120,
        win_rate=0.58,
        profit_factor=1.6,
        sharpe=1.2,
        max_drawdown=-0.07,
        total_return=0.18,
        status=BacktestStatus.PASSED,
    )

    report = compare_to_event_level_baselines(
        signal,
        backtest,
        candles=_event_candles(),
        funding_rates=_event_funding_rates(),
    )
    names = {item.name for item in report.baselines}

    assert "funding_extreme_only_event" in names
    assert "funding_plus_oi_event" in names
    assert "simple_failed_breakout_event" in names
    assert "opposite_direction_event" in names
    assert "buy_and_hold_event" in names
    assert not any(name.endswith("_proxy") for name in names)
    assert report.return_basis == "net_after_costs"
    assert all(item.net_return == item.total_return for item in report.baselines)
    assert any("event-level baseline" in finding for finding in report.findings)


def test_event_baselines_tolerate_mixed_datetime_awareness() -> None:
    signal = MarketSignal(
        signal_id="signal_funding_event_timezones",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=88,
        features={},
        hypothesis="funding crowding with historical open interest",
        data_sources=["ohlcv", "funding", "oi"],
    )
    backtest = BacktestReport(
        backtest_id="bt_funding_timezones",
        strategy_id="strategy_funding_timezones",
        timerange="20240101-20260501",
        trades=120,
        win_rate=0.58,
        profit_factor=1.6,
        sharpe=1.2,
        max_drawdown=-0.07,
        total_return=0.18,
        status=BacktestStatus.PASSED,
    )

    report = compare_to_event_level_baselines(
        signal,
        backtest,
        candles=_event_candles(aware=True),
        funding_rates=_event_funding_rates(aware=True),
        open_interest_points=_event_open_interest_points(),
    )

    assert any(item.name == "funding_plus_oi_event" for item in report.baselines)
    assert any("historical open-interest" in finding for finding in report.findings)


def _event_candles(count: int = 180, *, aware: bool = False) -> list[OhlcvCandle]:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc) if aware else datetime(2026, 5, 1)
    candles = []
    for index in range(count):
        open_time = start + timedelta(minutes=5 * index)
        base = 100 + index * 0.08
        close = base
        high = base + 0.2
        low = base - 0.5
        if index in {80, 120, 160}:
            high = base + 4
            close = base - 1
            low = close - 0.5
        candles.append(
            OhlcvCandle(
                symbol="BTC/USDT:USDT",
                interval="5m",
                open_time=open_time,
                close_time=open_time + timedelta(minutes=5),
                open=base - 0.1,
                high=high,
                low=low,
                close=close,
                volume=100 + index,
                quote_volume=close * (100 + index),
                trade_count=100 + index,
                raw=[],
            )
        )
    return candles


def _event_funding_rates(count: int = 180, *, aware: bool = False) -> list[FundingRatePoint]:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc) if aware else datetime(2026, 5, 1)
    return [
        FundingRatePoint(
            symbol="BTC/USDT:USDT",
            funding_time=start + timedelta(minutes=5 * index),
            funding_rate=0.00001 + index * 0.000001,
            mark_price=None,
            raw={},
        )
        for index in range(count)
    ]


def _event_open_interest_points(count: int = 180) -> list[OpenInterestPoint]:
    start = datetime(2026, 5, 1)
    return [
        OpenInterestPoint(
            symbol="BTC/USDT:USDT",
            timestamp=start + timedelta(minutes=5 * index),
            open_interest=1000 + index,
            raw={},
        )
        for index in range(count)
    ]
