from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from app.models import DataSufficiencyLevel, ResearchTask, ResearchTaskStatus, ResearchTaskType
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
