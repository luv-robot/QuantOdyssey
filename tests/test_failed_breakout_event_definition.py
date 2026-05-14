from datetime import datetime, timedelta

from app.models import (
    DataSufficiencyLevel,
    OhlcvCandle,
    ResearchTask,
    ResearchTaskType,
    StrategyFamily,
)
from app.services.harness import (
    build_failed_breakout_universe_report,
    run_failed_breakout_event_definition_sensitivity,
)
from app.storage import QuantRepository


def test_failed_breakout_event_definition_generates_report() -> None:
    task = _sample_task()
    report = run_failed_breakout_event_definition_sensitivity(
        task=task,
        candles=_sample_candles(),
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        level_lookback_bars=(24, 48),
        breakout_depth_bps=(10, 25),
        acceptance_window_bars=(3, 6),
        volume_zscore_thresholds=(0, 1.5),
        horizon_hours=1,
        min_trade_count=2,
    )

    assert report.task_id == task.task_id
    assert report.completed_trials == 16
    assert report.search_budget_trials == 16
    assert report.best_trial is not None
    assert report.best_trial.trade_count > 0
    assert report.simple_failed_breakout_trade_count > 0
    assert report.robust_trial_count >= 1
    assert any("Failed Breakout" in item for item in report.findings)


def test_failed_breakout_universe_report_summarizes_cross_market_stability() -> None:
    task = _sample_task()
    btc_report = run_failed_breakout_event_definition_sensitivity(
        task=task,
        candles=_sample_candles(symbol="BTC/USDT:USDT"),
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        level_lookback_bars=(24, 48),
        breakout_depth_bps=(10, 25),
        acceptance_window_bars=(3, 6),
        volume_zscore_thresholds=(0, 1.5),
        horizon_hours=1,
        min_trade_count=2,
    )
    eth_report = run_failed_breakout_event_definition_sensitivity(
        task=task,
        candles=_sample_candles(symbol="ETH/USDT:USDT"),
        symbol="ETH/USDT:USDT",
        timeframe="5m",
        level_lookback_bars=(24, 48),
        breakout_depth_bps=(10, 25),
        acceptance_window_bars=(3, 6),
        volume_zscore_thresholds=(0, 1.5),
        horizon_hours=1,
        min_trade_count=2,
    )

    universe = build_failed_breakout_universe_report(
        task=task,
        reports=[btc_report, eth_report],
        min_market_confirmations=2,
        min_trade_count=2,
    )

    assert universe.completed_cells == 2
    assert universe.symbols == ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    assert universe.robust_trial_ids
    assert len(universe.cells) == 2
    assert btc_report.report_id in universe.child_report_ids


def test_repository_persists_failed_breakout_reports() -> None:
    repository = QuantRepository()
    task = _sample_task()
    report = run_failed_breakout_event_definition_sensitivity(
        task=task,
        candles=_sample_candles(),
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        level_lookback_bars=(24, 48),
        breakout_depth_bps=(10, 25),
        acceptance_window_bars=(3, 6),
        volume_zscore_thresholds=(0, 1.5),
        horizon_hours=1,
        min_trade_count=2,
    )
    universe = build_failed_breakout_universe_report(
        task=task,
        reports=[report],
        min_market_confirmations=1,
        min_trade_count=2,
    )

    repository.save_failed_breakout_sensitivity_report(report)
    repository.save_failed_breakout_universe_report(universe)

    assert repository.get_failed_breakout_sensitivity_report(report.report_id) == report
    assert repository.query_failed_breakout_sensitivity_reports(task_id=task.task_id) == [report]
    assert repository.query_failed_breakout_sensitivity_reports(symbol="BTC/USDT:USDT") == [report]
    assert repository.get_failed_breakout_universe_report(universe.report_id) == universe
    assert repository.query_failed_breakout_universe_reports(thesis_id=task.thesis_id) == [universe]


def _sample_task() -> ResearchTask:
    return ResearchTask(
        task_id="task_failed_breakout_test",
        task_type=ResearchTaskType.EVENT_DEFINITION_TEST,
        subject_type="strategy_family",
        subject_id=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        thesis_id="thesis_failed_breakout",
        signal_id="signal_failed_breakout",
        hypothesis="Failed breakout needs enough events and must beat a simple failed-breakout baseline.",
        rationale="Funding templates were too low frequency under current data coverage.",
        required_experiments=["bounded OHLCV-only event-definition matrix"],
        success_metrics=["stable region beats simple baseline"],
        failure_conditions=["sample count collapses"],
        required_data_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
        estimated_cost=30,
        priority_score=91,
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
