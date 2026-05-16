from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from app.models import (
    BacktestReport,
    BacktestStatus,
    DataSufficiencyLevel,
    FailedBreakoutUniverseCell,
    FailedBreakoutUniverseReport,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    StrategyFamily,
    TradeRecord,
)
from app.services.harness import (
    HarnessRunnerConfig,
    read_scratchpad_events,
    run_research_harness_queue,
    seed_unattended_research_tasks,
)
from app.storage import QuantRepository


def test_harness_runner_executes_data_sufficiency_task(tmp_path) -> None:
    repository = QuantRepository()
    task = _task(
        task_id="task_data_review",
        task_type=ResearchTaskType.DATA_SUFFICIENCY_REVIEW,
        required_experiments=["missing funding history", "decide whether OHLCV proxy is acceptable"],
    )
    repository.save_research_task(task)

    summary = run_research_harness_queue(
        repository,
        config=HarnessRunnerConfig(max_tasks=3, scratchpad_base_dir=tmp_path),
    )

    assert summary.executed == 1
    assert summary.completed == 1
    assert repository.get_research_task(task.task_id).status == ResearchTaskStatus.COMPLETED
    findings = repository.query_research_findings(thesis_id="thesis_runner")
    assert len(findings) == 1
    assert findings[0].finding_type == "data_sufficiency_review"
    assert "missing funding history" in findings[0].evidence_gaps
    assert read_scratchpad_events(run_id=summary.run_id, base_dir=tmp_path)


def test_harness_runner_executes_baseline_task_with_local_ohlcv(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_ohlcv(data_dir / "BTC_USDT_USDT-5m-futures.feather", start_price=100)
    _write_ohlcv(data_dir / "ETH_USDT_USDT-5m-futures.feather", start_price=50)
    repository = QuantRepository()
    task = _task(
        task_id="task_baseline",
        task_type=ResearchTaskType.BASELINE_TEST,
        required_experiments=["run passive, momentum, trend, and range baselines"],
    )
    repository.save_research_task(task)

    summary = run_research_harness_queue(
        repository,
        config=HarnessRunnerConfig(
            data_dir=data_dir,
            symbols=("BTC/USDT:USDT", "ETH/USDT:USDT"),
            timeframes=("5m",),
            max_tasks=2,
            scratchpad_base_dir=tmp_path / "scratchpad",
        ),
    )

    assert summary.completed == 1
    finding = repository.query_research_findings(thesis_id="thesis_runner")[0]
    assert finding.finding_type == "baseline_test"
    assert any("Best baseline family" in item for item in finding.observations)
    assert any("baseline_implied_regime" in ref for ref in finding.evidence_refs)


def test_harness_runner_skips_approval_required_task(tmp_path) -> None:
    repository = QuantRepository()
    task = _task(
        task_id="task_optimizer",
        task_type=ResearchTaskType.PARAMETER_SENSITIVITY_TEST,
        required_experiments=["run optimizer grid"],
        approval_required=True,
    )
    repository.save_research_task(task)

    summary = run_research_harness_queue(
        repository,
        config=HarnessRunnerConfig(max_tasks=3, scratchpad_base_dir=tmp_path),
    )

    assert summary.executed == 0
    assert summary.skipped == 1
    assert summary.results[0].skipped_reason == "approval_required"
    assert repository.get_research_task(task.task_id).status == ResearchTaskStatus.PROPOSED


def test_harness_runner_skipped_tasks_do_not_consume_execution_budget(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_ohlcv(data_dir / "BTC_USDT_USDT-5m-futures.feather", start_price=100)
    repository = QuantRepository()
    baseline_task = _task(
        task_id="task_budget_baseline",
        task_type=ResearchTaskType.BASELINE_TEST,
        required_experiments=["run baseline board"],
    ).model_copy(update={"created_at": datetime(2026, 1, 1, 10, 0)})
    unsupported_task = _task(
        task_id="task_budget_cross_symbol",
        task_type=ResearchTaskType.CROSS_SYMBOL_TEST,
        required_experiments=["run cross-symbol validation"],
    ).model_copy(update={"created_at": datetime(2026, 1, 1, 11, 0)})
    repository.save_research_task(baseline_task)
    repository.save_research_task(unsupported_task)

    summary = run_research_harness_queue(
        repository,
        config=HarnessRunnerConfig(
            data_dir=data_dir,
            symbols=("BTC/USDT:USDT",),
            timeframes=("5m",),
            max_tasks=1,
            max_queue_scan=5,
            scratchpad_base_dir=tmp_path / "scratchpad",
        ),
    )

    assert summary.considered == 2
    assert summary.executed == 1
    assert summary.skipped == 1
    assert repository.get_research_task(baseline_task.task_id).status == ResearchTaskStatus.COMPLETED
    assert repository.get_research_task(unsupported_task.task_id).status == ResearchTaskStatus.PROPOSED


def test_harness_runner_executes_failed_breakout_walk_forward_task(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_failed_breakout_ohlcv(data_dir / "BTC_USDT_USDT-5m-futures.feather")
    repository = QuantRepository()
    universe = _failed_breakout_universe()
    repository.save_failed_breakout_universe_report(universe)
    task = _task(
        task_id="task_walk_forward",
        task_type=ResearchTaskType.WALK_FORWARD_TEST,
        required_experiments=["run walk-forward split by time"],
    ).model_copy(
        update={
            "subject_type": "strategy_family",
            "subject_id": StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
            "evidence_refs": [f"failed_breakout_universe_report:{universe.report_id}"],
        }
    )
    repository.save_research_task(task)

    summary = run_research_harness_queue(
        repository,
        config=HarnessRunnerConfig(
            data_dir=data_dir,
            symbols=("BTC/USDT:USDT",),
            timeframes=("5m",),
            max_tasks=1,
            walk_forward_min_trades_per_window=1,
            walk_forward_horizon_hours=1,
            scratchpad_base_dir=tmp_path / "scratchpad",
        ),
    )

    assert summary.completed == 1
    finding = repository.query_research_findings(thesis_id="thesis_runner")[0]
    assert finding.finding_type == "strategy_family_walk_forward_test"
    report_id = next(
        ref.split(":", 1)[1] for ref in finding.evidence_refs if ref.startswith("strategy_family_walk_forward_report:")
    )
    report = repository.get_strategy_family_walk_forward_report(report_id)
    assert report is not None
    assert report.source_universe_report_id == universe.report_id
    assert report.completed_windows == 3


def test_harness_runner_executes_regime_bucket_task_with_trades(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_ohlcv(data_dir / "BTC_USDT_USDT-5m-futures.feather", start_price=100)
    repository = QuantRepository()
    for trade in _sample_trades("strategy_runner"):
        repository.save_trade(trade)
    task = _task(
        task_id="task_regime",
        task_type=ResearchTaskType.REGIME_BUCKET_TEST,
        required_experiments=["bucket trades by regime"],
    ).model_copy(
        update={
            "subject_type": "strategy",
            "subject_id": "strategy_runner",
            "strategy_id": "strategy_runner",
        }
    )
    repository.save_research_task(task)

    summary = run_research_harness_queue(
        repository,
        config=HarnessRunnerConfig(
            data_dir=data_dir,
            symbols=("BTC/USDT:USDT",),
            timeframes=("5m",),
            max_tasks=1,
            scratchpad_base_dir=tmp_path / "scratchpad",
        ),
    )

    assert summary.completed == 1
    finding = repository.query_research_findings(thesis_id="thesis_runner")[0]
    assert finding.finding_type == "regime_bucket_test"
    assert any("trade_bucket=" in item for item in finding.observations)
    assert any("regime_coverage_report" in ref for ref in finding.evidence_refs)


def test_harness_runner_executes_strategy_monte_carlo_task(tmp_path) -> None:
    repository = QuantRepository()
    backtest = BacktestReport(
        backtest_id="backtest_strategy_runner",
        strategy_id="strategy_runner",
        timerange="20260101-20260102",
        trades=2,
        win_rate=0.5,
        profit_factor=2.0,
        sharpe=0.4,
        max_drawdown=-0.02,
        total_return=0.02,
        status=BacktestStatus.PASSED,
    )
    repository.save_backtest(backtest)
    for trade in _sample_trades("strategy_runner"):
        repository.save_trade(trade)
    task = _task(
        task_id="task_monte_carlo",
        task_type=ResearchTaskType.MONTE_CARLO_TEST,
        required_experiments=["run trade-level bootstrap"],
    ).model_copy(
        update={
            "subject_type": "strategy",
            "subject_id": "strategy_runner",
            "strategy_id": "strategy_runner",
        }
    )
    repository.save_research_task(task)

    summary = run_research_harness_queue(
        repository,
        config=HarnessRunnerConfig(
            max_tasks=1,
            monte_carlo_simulations=30,
            monte_carlo_horizon_trades=5,
            scratchpad_base_dir=tmp_path,
        ),
    )

    assert summary.completed == 1
    finding = repository.query_research_findings(thesis_id="thesis_runner")[0]
    assert finding.finding_type == "monte_carlo_test"
    report_id = next(ref.split(":", 1)[1] for ref in finding.evidence_refs if ref.startswith("monte_carlo_backtest:"))
    report = repository.get_monte_carlo_backtest(report_id)
    assert report is not None
    assert report.source_backtest_id == backtest.backtest_id
    assert report.approved_to_run is True


def test_seed_unattended_research_tasks_creates_daily_low_risk_queue() -> None:
    repository = QuantRepository()

    seeded = seed_unattended_research_tasks(repository, run_date=datetime(2026, 5, 16))
    seeded_again = seed_unattended_research_tasks(repository, run_date=datetime(2026, 5, 16))

    assert seeded_again == []
    assert {task.task_type for task in seeded} >= {
        ResearchTaskType.DATA_SUFFICIENCY_REVIEW,
        ResearchTaskType.BASELINE_TEST,
        ResearchTaskType.REGIME_BUCKET_TEST,
    }
    assert all(task.approval_required is False for task in seeded)
    assert all(task.autonomy_level <= 2 for task in seeded)


def _task(
    *,
    task_id: str,
    task_type: ResearchTaskType,
    required_experiments: list[str],
    approval_required: bool = False,
) -> ResearchTask:
    return ResearchTask(
        task_id=task_id,
        task_type=task_type,
        subject_type="thesis",
        subject_id="thesis_runner",
        thesis_id="thesis_runner",
        signal_id="signal_runner",
        hypothesis="Harness runner should execute low-risk research tasks.",
        rationale="Test harness runner behavior.",
        required_experiments=required_experiments,
        success_metrics=["finding persisted"],
        failure_conditions=["task blocked"],
        required_data_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
        estimated_cost=10,
        priority_score=80,
        status=ResearchTaskStatus.PROPOSED,
        approval_required=approval_required,
        autonomy_level=1,
    )


def _write_ohlcv(path, *, start_price: float) -> None:
    start = datetime(2026, 1, 1)
    rows = []
    price = start_price
    for index in range(160):
        price = price * (1 + 0.001 * ((index % 7) - 3) / 3)
        rows.append(
            {
                "date": start + timedelta(minutes=5 * index),
                "open": price,
                "high": price * 1.003,
                "low": price * 0.997,
                "close": price * (1 + 0.0005),
                "volume": 100 + index,
            }
        )
    pd.DataFrame(rows).to_feather(path)


def _write_failed_breakout_ohlcv(path) -> None:
    start = datetime(2026, 1, 1)
    winning_events = {60, 150, 240}
    losing_events = {105, 195, 285}
    all_events = winning_events | losing_events
    rows = []
    for index in range(330):
        timestamp = start + timedelta(minutes=5 * index)
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
        rows.append(
            {
                "date": timestamp,
                "open": open_,
                "high": max(high, open_, close),
                "low": min(low, open_, close),
                "close": close,
                "volume": volume,
            }
        )
    pd.DataFrame(rows).to_feather(path)


def _failed_breakout_universe() -> FailedBreakoutUniverseReport:
    trial_id = "trial_short_rolling_extreme_lb24_lq0_d10_aw3_af0_vz0"
    return FailedBreakoutUniverseReport(
        report_id="failed_breakout_universe_runner_test",
        thesis_id="thesis_runner",
        signal_id="signal_runner",
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        symbols=["BTC/USDT:USDT"],
        timeframes=["5m"],
        completed_cells=1,
        min_market_confirmations=1,
        robust_trial_ids=[trial_id],
        best_trial_frequency={trial_id: 1},
        cells=[
            FailedBreakoutUniverseCell(
                report_id="failed_breakout_btc_runner_test",
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


def _sample_trades(strategy_id: str) -> list[TradeRecord]:
    return [
        TradeRecord(
            trade_id=f"{strategy_id}_trade_1",
            strategy_id=strategy_id,
            symbol="BTC/USDT:USDT",
            opened_at=datetime(2026, 1, 1, 1, 0),
            closed_at=datetime(2026, 1, 1, 1, 30),
            entry_price=100,
            exit_price=103,
            quantity=1,
            profit_abs=3,
            profit_pct=0.03,
            fees=0.001,
        ),
        TradeRecord(
            trade_id=f"{strategy_id}_trade_2",
            strategy_id=strategy_id,
            symbol="BTC/USDT:USDT",
            opened_at=datetime(2026, 1, 1, 4, 0),
            closed_at=datetime(2026, 1, 1, 4, 30),
            entry_price=100,
            exit_price=99,
            quantity=1,
            profit_abs=-1,
            profit_pct=-0.01,
            fees=0.001,
        ),
    ]
