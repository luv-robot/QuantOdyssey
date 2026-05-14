from datetime import datetime, timedelta

from app.models import (
    DataSufficiencyLevel,
    FundingRatePoint,
    OhlcvCandle,
    OpenInterestPoint,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    StrategyFamily,
)
from app.services.harness import (
    build_event_definition_universe_report,
    run_funding_crowding_event_definition_sensitivity,
)
from app.storage import QuantRepository


def test_funding_crowding_event_definition_sensitivity_generates_report() -> None:
    task = _sample_task()
    report = run_funding_crowding_event_definition_sensitivity(
        task=task,
        candles=_sample_candles(),
        funding_rates=_sample_funding_rates(),
        open_interest_points=_sample_open_interest(),
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        min_trade_count=2,
    )

    assert report.task_id == task.task_id
    assert report.completed_trials == 108
    assert report.search_budget_trials == 108
    assert report.best_trial is not None
    assert report.best_trial.trade_count > 0
    assert report.robust_trial_count >= 1
    assert any("bounded event-definition" in item for item in report.findings)


def test_repository_persists_event_definition_sensitivity_report() -> None:
    repository = QuantRepository()
    task = _sample_task()
    report = run_funding_crowding_event_definition_sensitivity(
        task=task,
        candles=_sample_candles(),
        funding_rates=_sample_funding_rates(),
        open_interest_points=_sample_open_interest(),
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        min_trade_count=2,
    )

    repository.save_research_task(task.model_copy(update={"status": ResearchTaskStatus.COMPLETED}))
    repository.save_event_definition_sensitivity_report(report)

    assert repository.get_event_definition_sensitivity_report(report.report_id) == report
    assert repository.query_event_definition_sensitivity_reports(task_id=task.task_id) == [report]
    assert repository.query_event_definition_sensitivity_reports(symbol="BTC/USDT:USDT") == [report]


def test_universe_report_summarizes_cross_market_stability() -> None:
    task = _sample_task()
    btc_report = run_funding_crowding_event_definition_sensitivity(
        task=task,
        candles=_sample_candles(symbol="BTC/USDT:USDT"),
        funding_rates=_sample_funding_rates(symbol="BTC/USDT:USDT"),
        open_interest_points=_sample_open_interest(symbol="BTC/USDT:USDT"),
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        min_trade_count=2,
    )
    eth_report = run_funding_crowding_event_definition_sensitivity(
        task=task,
        candles=_sample_candles(symbol="ETH/USDT:USDT"),
        funding_rates=_sample_funding_rates(symbol="ETH/USDT:USDT"),
        open_interest_points=_sample_open_interest(symbol="ETH/USDT:USDT"),
        symbol="ETH/USDT:USDT",
        timeframe="5m",
        min_trade_count=2,
    )

    universe = build_event_definition_universe_report(
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


def test_repository_persists_event_definition_universe_report() -> None:
    repository = QuantRepository()
    task = _sample_task()
    report = run_funding_crowding_event_definition_sensitivity(
        task=task,
        candles=_sample_candles(),
        funding_rates=_sample_funding_rates(),
        open_interest_points=_sample_open_interest(),
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        min_trade_count=2,
    )
    universe = build_event_definition_universe_report(
        task=task,
        reports=[report],
        skipped_cells=["ETH/USDT:USDT:5m:missing_ohlcv"],
        min_market_confirmations=1,
        min_trade_count=2,
    )

    repository.save_event_definition_universe_report(universe)

    assert repository.get_event_definition_universe_report(universe.report_id) == universe
    assert repository.query_event_definition_universe_reports(thesis_id=task.thesis_id) == [universe]


def _sample_task() -> ResearchTask:
    return ResearchTask(
        task_id="task_event_definition_test",
        task_type=ResearchTaskType.EVENT_DEFINITION_TEST,
        subject_type="strategy_family",
        subject_id=StrategyFamily.FUNDING_CROWDING_FADE.value,
        thesis_id="thesis_funding_crowding",
        signal_id="signal_funding_crowding",
        hypothesis="Funding crowding fade requires a stricter event definition.",
        rationale="ReviewSession identified weak baseline performance.",
        required_experiments=["bounded event-definition matrix"],
        success_metrics=["stable region beats funding-only"],
        failure_conditions=["sample count collapses"],
        required_data_level=DataSufficiencyLevel.L1_FUNDING_OI,
        estimated_cost=40,
        priority_score=92,
    )


def _sample_candles(symbol: str = "BTC/USDT:USDT") -> list[OhlcvCandle]:
    start = datetime(2024, 1, 1)
    event_indices = {330, 390, 450, 510, 570, 630}
    candles: list[OhlcvCandle] = []
    for index in range(700):
        open_time = start + timedelta(minutes=5 * index)
        base = 100 + index * 0.01
        close = base
        high = base + 0.2
        low = base - 0.2
        if index + 1 in event_indices:
            high = base + 5
            close = base + 4
        if index in event_indices:
            high = base + 4
            close = base - 1
            low = close - 0.5
        for event_index in event_indices:
            if event_index < index <= event_index + 48:
                close = base - 2 - (index - event_index) * 0.03
                high = max(high, close + 0.3)
                low = min(low, close - 0.3)
        open_ = close + 0.05
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
                volume=1000 + index,
                quote_volume=(1000 + index) * close,
                trade_count=100 + index,
                raw=[],
            )
        )
    return candles


def _sample_funding_rates(symbol: str = "BTC/USDT:USDT") -> list[FundingRatePoint]:
    start = datetime(2024, 1, 1)
    points: list[FundingRatePoint] = []
    for index in range(60):
        funding_time = start + timedelta(hours=index)
        funding_rate = 0.0001 + index * 0.00001
        if index >= 24:
            funding_rate = 0.001 + index * 0.00002
        points.append(
            FundingRatePoint(
                symbol=symbol,
                funding_time=funding_time,
                funding_rate=funding_rate,
                raw={"date": funding_time.isoformat(), "fundingRate": funding_rate},
            )
        )
    return points


def _sample_open_interest(symbol: str = "BTC/USDT:USDT") -> list[OpenInterestPoint]:
    start = datetime(2024, 1, 1)
    event_indices = {330, 390, 450, 510, 570, 630}
    points: list[OpenInterestPoint] = []
    for index in range(700):
        timestamp = start + timedelta(minutes=5 * index)
        open_interest = 10_000 + index * 20
        if index in event_indices:
            open_interest -= 160
        points.append(
            OpenInterestPoint(
                symbol=symbol,
                timestamp=timestamp,
                open_interest=open_interest,
                raw={"timestamp": timestamp.isoformat(), "open_interest": open_interest},
            )
        )
    return points
