from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.models import (
    DataSufficiencyLevel,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    StrategyFamily,
)


def seed_unattended_research_tasks(
    repository,
    *,
    run_date: datetime | None = None,
    max_backtest_monte_carlo_tasks: int = 3,
) -> list[ResearchTask]:
    """Seed bounded daily maintenance tasks for the private mining machine.

    These tasks are deliberately low-autonomy and low-cost. They keep evidence collection moving
    when the user is away without letting the Harness invent new strategy searches.
    """

    day = (run_date or datetime.utcnow()).strftime("%Y%m%d")
    tasks: list[ResearchTask] = [
        _system_task(
            task_id=f"task_daily_data_sufficiency_{day}",
            task_type=ResearchTaskType.DATA_SUFFICIENCY_REVIEW,
            hypothesis="Daily unattended research should first record whether current free data coverage is sufficient.",
            rationale="Data gaps and stale feeds can invalidate downstream baseline, regime, and validation conclusions.",
            required_experiments=[
                "check OHLCV availability for configured symbols and timeframes",
                "check orderflow freshness through the system health monitor",
                "record unavailable funding, OI, or tick-level evidence as explicit limitations",
            ],
            success_metrics=["data coverage gaps are visible in ResearchFinding", "no missing data is silently treated as evidence"],
            failure_conditions=["no market data cells load", "collector health check is failing"],
            priority_score=86,
            estimated_cost=8,
        ),
        _system_task(
            task_id=f"task_daily_baseline_board_{day}",
            task_type=ResearchTaskType.BASELINE_TEST,
            hypothesis="Baseline families should be rerun regularly so strategy conclusions are judged against current data context.",
            rationale="Passive, momentum, trend, and mean-reversion baselines provide a calibration surface for regime inference.",
            required_experiments=[
                "run passive BTC buy-and-hold, BTC DCA, equal-weight, momentum, trend, and mean-reversion/grid-like baselines",
                "compare returns, profit factor, Sharpe, max drawdown, trade count, and tested cells",
            ],
            success_metrics=["best baseline family is identified", "baseline-implied regime evidence is updated"],
            failure_conditions=["baseline board cannot load OHLCV cells"],
            priority_score=84,
            estimated_cost=20,
        ),
        _system_task(
            task_id=f"task_daily_regime_bucket_{day}",
            task_type=ResearchTaskType.REGIME_BUCKET_TEST,
            hypothesis="Regime evidence should be inferred from the current baseline and OHLCV coverage before strategy-specific tuning.",
            rationale="The system should avoid optimizing a strategy against a single smooth or misleading data segment.",
            required_experiments=[
                "bucket available OHLCV cells by trend, range, high-volatility, and low-volatility states",
                "if strategy trades are available, summarize trade outcomes by regime bucket",
            ],
            success_metrics=["dominant regime is visible", "coverage imbalance is flagged"],
            failure_conditions=["no candles are available for regime coverage"],
            priority_score=78,
            estimated_cost=18,
        ),
    ]
    tasks.extend(_failed_breakout_validation_tasks(repository, day))
    tasks.extend(_strategy_monte_carlo_tasks(repository, day, limit=max_backtest_monte_carlo_tasks))

    saved: list[ResearchTask] = []
    for task in tasks:
        if repository.get_research_task(task.task_id) is not None:
            continue
        repository.save_research_task(task)
        saved.append(task)
    return saved


def _failed_breakout_validation_tasks(repository, day: str) -> list[ResearchTask]:
    reports = repository.query_failed_breakout_universe_reports(
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        limit=1,
    )
    if not reports:
        return []
    report = reports[0]
    subject_id = StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value
    common = {
        "subject_type": "strategy_family",
        "subject_id": subject_id,
        "thesis_id": report.thesis_id,
        "signal_id": report.signal_id or "signal_daily_failed_breakout_validation",
        "strategy_id": None,
        "required_data_level": DataSufficiencyLevel.L0_OHLCV_ONLY,
        "status": ResearchTaskStatus.PROPOSED,
        "approval_required": False,
        "autonomy_level": 2,
        "evidence_refs": [f"failed_breakout_universe_report:{report.report_id}"],
    }
    return [
        ResearchTask(
            task_id=f"task_daily_failed_breakout_walk_forward_{day}_{report.report_id}",
            task_type=ResearchTaskType.WALK_FORWARD_TEST,
            hypothesis="Failed Breakout family evidence should survive simple walk-forward splits before deeper optimization.",
            rationale="The latest universe scan is replayable, so walk-forward validation is a low-risk follow-up.",
            required_experiments=["split replayable event trials by time", "compare pass rate across folds"],
            success_metrics=["pass_rate >= configured threshold", "completed_windows > 0"],
            failure_conditions=["no replayable windows complete", "pass_rate remains below threshold"],
            priority_score=82,
            estimated_cost=35,
            **common,
        ),
        ResearchTask(
            task_id=f"task_daily_failed_breakout_monte_carlo_{day}_{report.report_id}",
            task_type=ResearchTaskType.MONTE_CARLO_TEST,
            hypothesis="Failed Breakout family path risk should be checked with bounded bootstrap Monte Carlo.",
            rationale="Monte Carlo converts event-trial dispersion into drawdown and loss-probability evidence.",
            required_experiments=["bootstrap event trial returns", "report median return, p05 return, and loss probability"],
            success_metrics=["median_return > 0", "probability_of_loss < configured threshold"],
            failure_conditions=["simulation requires human confirmation", "sampled_trade_count is too low"],
            priority_score=80,
            estimated_cost=40,
            **common,
        ),
    ]


def _strategy_monte_carlo_tasks(repository, day: str, *, limit: int) -> list[ResearchTask]:
    tasks: list[ResearchTask] = []
    for backtest in repository.query_backtests(limit=limit):
        task_id = f"task_daily_strategy_monte_carlo_{day}_{backtest.backtest_id}"
        tasks.append(
            ResearchTask(
                task_id=task_id,
                task_type=ResearchTaskType.MONTE_CARLO_TEST,
                subject_type="strategy",
                subject_id=backtest.strategy_id,
                thesis_id=None,
                signal_id="signal_daily_strategy_monte_carlo",
                strategy_id=backtest.strategy_id,
                hypothesis="Any strategy with a backtest should expose path-risk before it is considered for watchlist or paper review.",
                rationale=f"Backtest `{backtest.backtest_id}` is available for bounded strategy-level Monte Carlo.",
                required_experiments=["run trade-level bootstrap when trades exist", "otherwise run derived return distribution Monte Carlo"],
                success_metrics=["median_return > 0", "probability_of_loss < 45%", "p05_return remains within loss budget"],
                failure_conditions=["missing source backtest", "loss probability remains high", "requires expensive simulation approval"],
                required_data_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
                estimated_cost=30,
                priority_score=74,
                status=ResearchTaskStatus.PROPOSED,
                approval_required=False,
                autonomy_level=2,
                evidence_refs=[f"backtest:{backtest.backtest_id}"],
            )
        )
    return tasks


def _system_task(
    *,
    task_id: str,
    task_type: ResearchTaskType,
    hypothesis: str,
    rationale: str,
    required_experiments: list[str],
    success_metrics: list[str],
    failure_conditions: list[str],
    priority_score: float,
    estimated_cost: int,
) -> ResearchTask:
    return ResearchTask(
        task_id=task_id,
        task_type=task_type,
        subject_type="system",
        subject_id="unattended_research_maintenance",
        thesis_id=None,
        signal_id=f"signal_unattended_{uuid4().hex[:8]}",
        strategy_id=None,
        hypothesis=hypothesis,
        rationale=rationale,
        required_experiments=required_experiments,
        success_metrics=success_metrics,
        failure_conditions=failure_conditions,
        required_data_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
        estimated_cost=estimated_cost,
        priority_score=priority_score,
        status=ResearchTaskStatus.PROPOSED,
        approval_required=False,
        autonomy_level=1,
        evidence_refs=["supervisor_policy:unattended_low_risk_research"],
    )
