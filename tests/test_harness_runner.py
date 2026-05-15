from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from app.models import (
    BacktestReport,
    BacktestStatus,
    DataSufficiencyLevel,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    TradeRecord,
)
from app.services.harness import HarnessRunnerConfig, read_scratchpad_events, run_research_harness_queue
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
        task_id="task_budget_walk_forward",
        task_type=ResearchTaskType.WALK_FORWARD_TEST,
        required_experiments=["run walk-forward validation"],
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
