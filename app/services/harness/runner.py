from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import pstdev
from uuid import uuid4

from app.models import (
    MonteCarloBacktestConfig,
    DataSufficiencyLevel,
    FailedBreakoutUniverseReport,
    OhlcvCandle,
    ResearchFinding,
    ResearchFindingSeverity,
    ResearchScratchpadRun,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    ScratchpadEventType,
    StrategyFamily,
    TradeRecord,
)
from app.services.backtester import run_monte_carlo_backtest, run_trade_bootstrap_monte_carlo
from app.services.harness.event_definition import (
    build_event_definition_universe_report,
    build_failed_breakout_universe_report,
    run_failed_breakout_event_definition_sensitivity,
    run_funding_crowding_event_definition_sensitivity,
)
from app.services.harness.scratchpad import append_scratchpad_event, create_scratchpad_run
from app.services.harness.screening import (
    build_baseline_implied_regime_report,
    build_regime_coverage_report,
    build_strategy_family_baseline_board,
    build_strategy_family_baseline_boards_by_timeframe,
)
from app.services.reviewer import build_baseline_board_review
from app.services.harness.validation import (
    run_failed_breakout_bootstrap_monte_carlo,
    run_failed_breakout_walk_forward_validation,
)
from app.services.market_data import (
    find_freqtrade_funding_file,
    find_open_interest_file,
    load_freqtrade_funding_rates,
    load_freqtrade_ohlcv,
    load_open_interest_points,
)


SUPPORTED_AUTOMATIC_TASK_TYPES = {
    ResearchTaskType.DATA_SUFFICIENCY_REVIEW,
    ResearchTaskType.BASELINE_TEST,
    ResearchTaskType.EVENT_FREQUENCY_SCAN,
    ResearchTaskType.REGIME_BUCKET_TEST,
    ResearchTaskType.MONTE_CARLO_TEST,
    ResearchTaskType.WALK_FORWARD_TEST,
}


@dataclass(frozen=True)
class HarnessRunnerConfig:
    data_dir: Path = Path("freqtrade_user_data/data/binance/futures")
    symbols: tuple[str, ...] = ("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT")
    timeframes: tuple[str, ...] = ("5m", "15m")
    max_tasks: int = 5
    max_queue_scan: int = 50
    max_candles: int = 5000
    max_trials: int = 80
    min_trade_count: int = 20
    monte_carlo_simulations: int = 200
    monte_carlo_horizon_trades: int = 50
    monte_carlo_seed: int | None = 7
    monte_carlo_expensive_threshold: int = 250_000
    approve_expensive_monte_carlo: bool = False
    walk_forward_folds: int = 3
    walk_forward_min_trades_per_window: int = 20
    walk_forward_min_pass_rate: float = 0.5
    walk_forward_horizon_hours: int = 2
    walk_forward_fee_rate: float = 0.001
    walk_forward_slippage_bps: float = 2.0
    walk_forward_funding_rate_8h: float = 0.0
    scratchpad_base_dir: Path = Path(".qo") / "scratchpad"


@dataclass(frozen=True)
class HarnessTaskRunResult:
    task_id: str
    task_type: str
    status: ResearchTaskStatus
    finding_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


@dataclass(frozen=True)
class HarnessQueueRunSummary:
    run_id: str
    considered: int
    executed: int
    skipped: int
    completed: int
    blocked: int
    results: list[HarnessTaskRunResult]
    scratchpad_path: str


def run_research_harness_queue(
    repository,
    *,
    config: HarnessRunnerConfig | None = None,
) -> HarnessQueueRunSummary:
    config = config or HarnessRunnerConfig()
    run_id = f"harness_runner_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
    scratchpad_run = create_scratchpad_run(
        run_id=run_id,
        purpose="automatic_low_risk_research_task_execution",
        base_dir=config.scratchpad_base_dir,
    )
    proposed_tasks = repository.query_research_tasks(
        status=ResearchTaskStatus.PROPOSED.value,
        limit=max(config.max_tasks, config.max_queue_scan),
    )
    results: list[HarnessTaskRunResult] = []
    for task in proposed_tasks:
        result = _run_one_task(repository, task, config=config, scratchpad_run=scratchpad_run)
        results.append(result)
        if sum(1 for item in results if item.skipped_reason is None) >= config.max_tasks:
            break

    executed = sum(1 for result in results if result.skipped_reason is None)
    completed = sum(1 for result in results if result.status == ResearchTaskStatus.COMPLETED)
    blocked = sum(1 for result in results if result.status == ResearchTaskStatus.BLOCKED)
    summary = HarnessQueueRunSummary(
        run_id=run_id,
        considered=len(results),
        executed=executed,
        skipped=len(results) - executed,
        completed=completed,
        blocked=blocked,
        results=results,
        scratchpad_path=scratchpad_run.scratchpad_path,
    )
    append_scratchpad_event(
        run_id=run_id,
        event_type=ScratchpadEventType.NOTE,
        payload={
            "summary": {
                "considered": summary.considered,
                "executed": summary.executed,
                "skipped": summary.skipped,
                "completed": summary.completed,
                "blocked": summary.blocked,
            }
        },
        base_dir=config.scratchpad_base_dir,
    )
    return summary


def _run_one_task(
    repository,
    task: ResearchTask,
    *,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> HarnessTaskRunResult:
    skip_reason = _skip_reason(task)
    if skip_reason is not None:
        append_scratchpad_event(
            run_id=scratchpad_run.run_id,
            event_type=ScratchpadEventType.RESEARCH_TASK,
            payload={"task": task.model_dump(mode="json"), "skipped_reason": skip_reason},
            task_id=task.task_id,
            thesis_id=task.thesis_id,
            strategy_id=task.strategy_id,
            evidence_refs=task.evidence_refs,
            base_dir=config.scratchpad_base_dir,
        )
        return HarnessTaskRunResult(
            task_id=task.task_id,
            task_type=task.task_type.value,
            status=task.status,
            skipped_reason=skip_reason,
        )

    running = task.model_copy(update={"status": ResearchTaskStatus.RUNNING})
    repository.save_research_task(running)
    append_scratchpad_event(
        run_id=scratchpad_run.run_id,
        event_type=ScratchpadEventType.RESEARCH_TASK,
        payload={"task": running.model_dump(mode="json"), "state": "started"},
        task_id=task.task_id,
        thesis_id=task.thesis_id,
        strategy_id=task.strategy_id,
        evidence_refs=task.evidence_refs,
        base_dir=config.scratchpad_base_dir,
    )
    try:
        findings, artifact_refs = _execute_task(repository, running, config=config, scratchpad_run=scratchpad_run)
        final_status = ResearchTaskStatus.COMPLETED
    except Exception as exc:  # pragma: no cover - defensive guardrail for production runner.
        findings = [
            _finding(
                task=running,
                finding_type="harness_task_error",
                severity=ResearchFindingSeverity.HIGH,
                summary=f"Harness task failed during automatic execution: {exc}",
                observations=[type(exc).__name__],
                evidence_gaps=["automatic_runner_exception"],
            )
        ]
        artifact_refs = []
        final_status = ResearchTaskStatus.BLOCKED

    saved_findings = []
    for finding in findings:
        repository.save_research_finding(finding)
        saved_findings.append(finding.finding_id)
        append_scratchpad_event(
            run_id=scratchpad_run.run_id,
            event_type=ScratchpadEventType.RESEARCH_FINDING,
            payload=finding.model_dump(mode="json"),
            task_id=task.task_id,
            thesis_id=task.thesis_id,
            strategy_id=task.strategy_id,
            evidence_refs=finding.evidence_refs,
            base_dir=config.scratchpad_base_dir,
        )
    completed_task = running.model_copy(update={"status": final_status})
    repository.save_research_task(completed_task)
    append_scratchpad_event(
        run_id=scratchpad_run.run_id,
        event_type=ScratchpadEventType.RESEARCH_TASK,
        payload={"task": completed_task.model_dump(mode="json"), "state": "finished", "artifact_refs": artifact_refs},
        task_id=task.task_id,
        thesis_id=task.thesis_id,
        strategy_id=task.strategy_id,
        evidence_refs=[*task.evidence_refs, *artifact_refs],
        base_dir=config.scratchpad_base_dir,
    )
    return HarnessTaskRunResult(
        task_id=task.task_id,
        task_type=task.task_type.value,
        status=final_status,
        finding_ids=saved_findings,
        artifact_refs=artifact_refs,
    )


def _skip_reason(task: ResearchTask) -> str | None:
    if task.approval_required:
        return "approval_required"
    if task.autonomy_level > 2:
        return f"autonomy_level_{task.autonomy_level}_requires_human_gate"
    if task.task_type not in SUPPORTED_AUTOMATIC_TASK_TYPES:
        return f"unsupported_automatic_task_type:{task.task_type.value}"
    return None


def _execute_task(
    repository,
    task: ResearchTask,
    *,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> tuple[list[ResearchFinding], list[str]]:
    if task.task_type == ResearchTaskType.DATA_SUFFICIENCY_REVIEW:
        return _execute_data_sufficiency_review(task), []
    if task.task_type == ResearchTaskType.BASELINE_TEST:
        return _execute_baseline_test(task, config=config, scratchpad_run=scratchpad_run), []
    if task.task_type == ResearchTaskType.EVENT_FREQUENCY_SCAN:
        return _execute_event_frequency_scan(repository, task, config=config, scratchpad_run=scratchpad_run)
    if task.task_type == ResearchTaskType.REGIME_BUCKET_TEST:
        return _execute_regime_bucket_test(repository, task, config=config, scratchpad_run=scratchpad_run)
    if task.task_type == ResearchTaskType.MONTE_CARLO_TEST:
        return _execute_monte_carlo_test(repository, task, config=config, scratchpad_run=scratchpad_run)
    if task.task_type == ResearchTaskType.WALK_FORWARD_TEST:
        return _execute_walk_forward_test(repository, task, config=config, scratchpad_run=scratchpad_run)
    raise ValueError(f"Unsupported Harness task type: {task.task_type.value}")


def _execute_data_sufficiency_review(task: ResearchTask) -> list[ResearchFinding]:
    gaps = [
        item
        for item in task.required_experiments
        if any(key in item.lower() for key in ["missing", "unavailable", "gap", "缺", "错配", "cannot"])
    ]
    severity = ResearchFindingSeverity.MEDIUM if gaps else ResearchFindingSeverity.LOW
    return [
        _finding(
            task=task,
            finding_type="data_sufficiency_review",
            severity=severity,
            summary="Harness completed a data sufficiency review for this research task.",
            observations=[
                f"required_data_level={task.required_data_level.value}",
                *task.required_experiments,
            ],
            evidence_gaps=gaps,
        )
    ]


def _execute_baseline_test(
    task: ResearchTask,
    *,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> list[ResearchFinding]:
    candles_by_cell, skipped = _load_candles_by_cell(config)
    if not candles_by_cell:
        return [
            _finding(
                task=task,
                finding_type="baseline_test",
                severity=ResearchFindingSeverity.HIGH,
                summary="Harness could not run baseline board because no OHLCV cells were available.",
                observations=[],
                evidence_gaps=skipped or ["no_ohlcv_cells_loaded"],
            )
        ]
    board = build_strategy_family_baseline_board(candles_by_cell)
    timeframe_boards = build_strategy_family_baseline_boards_by_timeframe(candles_by_cell)
    regime = build_baseline_implied_regime_report(board)
    review = build_baseline_board_review(board, regime=regime, timeframe_boards=timeframe_boards)
    append_scratchpad_event(
        run_id=scratchpad_run.run_id,
        event_type=ScratchpadEventType.NOTE,
        payload={
            "baseline_board": board.model_dump(mode="json"),
            "baseline_boards_by_timeframe": {
                timeframe: item.model_dump(mode="json") for timeframe, item in timeframe_boards.items()
            },
            "baseline_implied_regime": regime.model_dump(mode="json"),
            "baseline_board_review": review.model_dump(mode="json"),
            "skipped_cells": skipped,
        },
        task_id=task.task_id,
        thesis_id=task.thesis_id,
        strategy_id=task.strategy_id,
        evidence_refs=[f"research_task:{task.task_id}"],
        base_dir=config.scratchpad_base_dir,
    )
    rows = [
        (
            f"{row.strategy_family}: net={row.total_return:.4f}, gross={row.gross_return:.4f}, "
            f"cost_drag={row.cost_drag:.4f}, pf={row.profit_factor:.4f}, trades={row.trades}"
        )
        for row in board.rows
    ]
    return [
        _finding(
            task=task,
            finding_type="baseline_test",
            severity=ResearchFindingSeverity.LOW,
            summary=f"Harness ran baseline board; best family is {board.best_family or 'unknown'}.",
            observations=[
                *board.findings,
                *regime.findings,
                review.summary,
                *[claim.statement for claim in review.evidence_against],
                *[f"Next experiment: {item}" for item in review.next_experiments],
                *rows,
            ],
            evidence_gaps=skipped,
            evidence_refs=[
                f"scratchpad:{scratchpad_run.run_id}:strategy_family_baseline_board:{board.board_id}",
                f"scratchpad:{scratchpad_run.run_id}:baseline_board_review:{review.review_id}",
                f"scratchpad:{scratchpad_run.run_id}:baseline_implied_regime:{regime.report_id}",
            ],
        )
    ]


def _execute_event_frequency_scan(
    repository,
    task: ResearchTask,
    *,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> tuple[list[ResearchFinding], list[str]]:
    family = _task_strategy_family(task)
    if family == StrategyFamily.FAILED_BREAKOUT_PUNISHMENT:
        return _run_failed_breakout_scan(repository, task, config=config, scratchpad_run=scratchpad_run)
    if family == StrategyFamily.FUNDING_CROWDING_FADE:
        return _run_funding_crowding_scan(repository, task, config=config, scratchpad_run=scratchpad_run)
    candles_by_cell, skipped = _load_candles_by_cell(config)
    observations = [
        f"{symbol}:{timeframe}:candles={len(candles)}"
        for (symbol, timeframe), candles in sorted(candles_by_cell.items())
    ]
    return [
        _finding(
            task=task,
            finding_type="event_frequency_scan",
            severity=ResearchFindingSeverity.MEDIUM,
            summary=(
                "Harness recorded OHLCV coverage but no specialized event-frequency executor exists "
                f"for `{family.value}` yet."
            ),
            observations=observations,
            evidence_gaps=skipped + [f"unsupported_event_frequency_family:{family.value}"],
        )
    ], []


def _run_failed_breakout_scan(
    repository,
    task: ResearchTask,
    *,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> tuple[list[ResearchFinding], list[str]]:
    reports = []
    skipped: list[str] = []
    for symbol in config.symbols:
        for timeframe in config.timeframes:
            path = _ohlcv_path(config.data_dir, symbol, timeframe)
            if not path.exists():
                skipped.append(f"{symbol}:{timeframe}:missing_ohlcv")
                continue
            candles = load_freqtrade_ohlcv(path, symbol, timeframe)
            if config.max_candles > 0 and len(candles) > config.max_candles:
                candles = candles[-config.max_candles :]
            report = run_failed_breakout_event_definition_sensitivity(
                task=task,
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                level_sources=("rolling_extreme",),
                level_lookback_bars=(48, 96),
                level_quality_thresholds=(0,),
                breakout_depth_bps=(10, 25, 50),
                acceptance_window_bars=(3, 6),
                acceptance_failure_thresholds=(0,),
                volume_zscore_thresholds=(0, 1.5),
                max_trials=config.max_trials,
                min_trade_count=max(10, config.min_trade_count),
                fee_rate=config.walk_forward_fee_rate,
                slippage_bps=config.walk_forward_slippage_bps,
                funding_rate_8h=config.walk_forward_funding_rate_8h,
            )
            reports.append(report)
            repository.save_failed_breakout_sensitivity_report(report)
    universe = build_failed_breakout_universe_report(
        task=task,
        reports=reports,
        skipped_cells=skipped,
        min_trade_count=max(10, config.min_trade_count),
    )
    repository.save_failed_breakout_universe_report(universe)
    append_scratchpad_event(
        run_id=scratchpad_run.run_id,
        event_type=ScratchpadEventType.NOTE,
        payload={"failed_breakout_universe_report": universe.model_dump(mode="json")},
        task_id=task.task_id,
        thesis_id=task.thesis_id,
        strategy_id=task.strategy_id,
        evidence_refs=[f"failed_breakout_universe_report:{universe.report_id}"],
        base_dir=config.scratchpad_base_dir,
    )
    severity = ResearchFindingSeverity.LOW if universe.robust_trial_ids else ResearchFindingSeverity.MEDIUM
    if universe.completed_cells == 0:
        severity = ResearchFindingSeverity.HIGH
    finding = _finding(
        task=task,
        finding_type="failed_breakout_event_frequency_scan",
        severity=severity,
        summary="Harness ran Failed Breakout event-frequency scan across the configured universe.",
        observations=universe.findings,
        evidence_gaps=universe.skipped_cells,
        evidence_refs=[f"failed_breakout_universe_report:{universe.report_id}"],
    )
    return [finding], [f"failed_breakout_universe_report:{universe.report_id}"]


def _run_funding_crowding_scan(
    repository,
    task: ResearchTask,
    *,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> tuple[list[ResearchFinding], list[str]]:
    reports = []
    skipped: list[str] = []
    for symbol in config.symbols:
        for timeframe in config.timeframes:
            ohlcv_file = _ohlcv_path(config.data_dir, symbol, timeframe)
            if not ohlcv_file.exists():
                skipped.append(f"{symbol}:{timeframe}:missing_ohlcv")
                continue
            funding_file = find_freqtrade_funding_file(ohlcv_file, symbol, timeframe)
            if funding_file is None:
                skipped.append(f"{symbol}:{timeframe}:missing_funding")
                continue
            oi_file = find_open_interest_file(ohlcv_file, symbol, timeframe) or _fallback_open_interest_file(
                config.data_dir, symbol
            )
            candles = load_freqtrade_ohlcv(ohlcv_file, symbol, timeframe)
            if config.max_candles > 0 and len(candles) > config.max_candles:
                candles = candles[-config.max_candles :]
            report = run_funding_crowding_event_definition_sensitivity(
                task=task,
                candles=candles,
                funding_rates=load_freqtrade_funding_rates(funding_file, symbol),
                open_interest_points=None if oi_file is None else load_open_interest_points(oi_file, symbol),
                symbol=symbol,
                timeframe=timeframe,
                max_trials=config.max_trials,
                min_trade_count=max(10, config.min_trade_count),
                fee_rate=config.walk_forward_fee_rate,
                slippage_bps=config.walk_forward_slippage_bps,
                funding_rate_8h=config.walk_forward_funding_rate_8h,
            )
            reports.append(report)
            repository.save_event_definition_sensitivity_report(report)
    universe = build_event_definition_universe_report(
        task=task,
        reports=reports,
        skipped_cells=skipped,
        min_trade_count=max(10, config.min_trade_count),
    )
    repository.save_event_definition_universe_report(universe)
    append_scratchpad_event(
        run_id=scratchpad_run.run_id,
        event_type=ScratchpadEventType.NOTE,
        payload={"event_definition_universe_report": universe.model_dump(mode="json")},
        task_id=task.task_id,
        thesis_id=task.thesis_id,
        strategy_id=task.strategy_id,
        evidence_refs=[f"event_definition_universe_report:{universe.report_id}"],
        base_dir=config.scratchpad_base_dir,
    )
    severity = ResearchFindingSeverity.LOW if universe.robust_trial_ids else ResearchFindingSeverity.MEDIUM
    if universe.completed_cells == 0:
        severity = ResearchFindingSeverity.HIGH
    finding = _finding(
        task=task,
        finding_type="funding_crowding_event_frequency_scan",
        severity=severity,
        summary="Harness ran Funding Crowding event-frequency scan across the configured universe.",
        observations=universe.findings,
        evidence_gaps=universe.skipped_cells,
        evidence_refs=[f"event_definition_universe_report:{universe.report_id}"],
    )
    return [finding], [f"event_definition_universe_report:{universe.report_id}"]


def _execute_regime_bucket_test(
    repository,
    task: ResearchTask,
    *,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> tuple[list[ResearchFinding], list[str]]:
    candles_by_cell, skipped = _load_candles_by_cell(config)
    if not candles_by_cell:
        return [
            _finding(
                task=task,
                finding_type="regime_bucket_test",
                severity=ResearchFindingSeverity.HIGH,
                summary="Harness could not run regime bucket test because no OHLCV cells were available.",
                observations=[],
                evidence_gaps=skipped or ["no_ohlcv_cells_loaded"],
            )
        ], []

    family = _task_strategy_family(task)
    coverage = build_regime_coverage_report(candles_by_cell, strategy_family=family)
    trades = repository.query_trades(strategy_id=task.strategy_id, limit=5000) if task.strategy_id else []
    trade_observations, trade_gaps = _trade_regime_observations(trades, candles_by_cell)
    append_scratchpad_event(
        run_id=scratchpad_run.run_id,
        event_type=ScratchpadEventType.NOTE,
        payload={
            "regime_coverage_report": coverage.model_dump(mode="json"),
            "trade_regime_buckets": trade_observations,
            "skipped_cells": skipped,
        },
        task_id=task.task_id,
        thesis_id=task.thesis_id,
        strategy_id=task.strategy_id,
        evidence_refs=[f"regime_coverage_report:{coverage.report_id}"],
        base_dir=config.scratchpad_base_dir,
    )
    severity = ResearchFindingSeverity.LOW
    if not coverage.is_coverage_balanced or trade_gaps:
        severity = ResearchFindingSeverity.MEDIUM
    if not coverage.buckets:
        severity = ResearchFindingSeverity.HIGH
    observations = [
        *coverage.findings,
        *[
            (
                f"{bucket.regime}: candles={bucket.candle_count}, share={bucket.share:.1%}, "
                f"avg_return={bucket.average_return:.6f}, vol={bucket.realized_volatility:.6f}, "
                f"trend_return={bucket.trend_return:.4f}"
            )
            for bucket in coverage.buckets
        ],
        *trade_observations,
    ]
    evidence_refs = [f"scratchpad:{scratchpad_run.run_id}:regime_coverage_report:{coverage.report_id}"]
    return [
        _finding(
            task=task,
            finding_type="regime_bucket_test",
            severity=severity,
            summary="Harness ran regime bucket coverage and, when available, trade-level regime bucketing.",
            observations=observations,
            evidence_gaps=[*skipped, *trade_gaps],
            evidence_refs=evidence_refs,
        )
    ], evidence_refs


def _execute_monte_carlo_test(
    repository,
    task: ResearchTask,
    *,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> tuple[list[ResearchFinding], list[str]]:
    family = _task_strategy_family(task)
    universe_report = _failed_breakout_universe_for_task(repository, task) if family == StrategyFamily.FAILED_BREAKOUT_PUNISHMENT else None
    if universe_report is not None:
        return _execute_failed_breakout_monte_carlo(
            repository,
            task,
            universe_report=universe_report,
            config=config,
            scratchpad_run=scratchpad_run,
        )
    return _execute_strategy_monte_carlo(repository, task, config=config, scratchpad_run=scratchpad_run)


def _execute_walk_forward_test(
    repository,
    task: ResearchTask,
    *,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> tuple[list[ResearchFinding], list[str]]:
    family = _task_strategy_family(task)
    universe_report = _failed_breakout_universe_for_task(repository, task) if family == StrategyFamily.FAILED_BREAKOUT_PUNISHMENT else None
    if universe_report is None:
        return [
            _finding(
                task=task,
                finding_type="walk_forward_test",
                severity=ResearchFindingSeverity.HIGH,
                summary="Harness could not run automatic walk-forward validation for this task.",
                observations=[
                    f"strategy_family={family.value}",
                    "Automatic walk-forward currently requires a strategy-family universe report with replayable event trials.",
                ],
                evidence_gaps=[
                    "missing_replayable_universe_report"
                    if family == StrategyFamily.FAILED_BREAKOUT_PUNISHMENT
                    else f"unsupported_walk_forward_family:{family.value}"
                ],
            )
        ], []
    return _execute_failed_breakout_walk_forward(
        repository,
        task,
        universe_report=universe_report,
        config=config,
        scratchpad_run=scratchpad_run,
    )


def _execute_failed_breakout_walk_forward(
    repository,
    task: ResearchTask,
    *,
    universe_report: FailedBreakoutUniverseReport,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> tuple[list[ResearchFinding], list[str]]:
    candles_by_cell, skipped = _load_candles_by_cell(
        config,
        symbols=tuple(universe_report.symbols or config.symbols),
        timeframes=tuple(universe_report.timeframes or config.timeframes),
    )
    report = run_failed_breakout_walk_forward_validation(
        universe_report=universe_report,
        candles_by_cell=candles_by_cell,
        folds=config.walk_forward_folds,
        min_trades_per_window=config.walk_forward_min_trades_per_window,
        min_pass_rate=config.walk_forward_min_pass_rate,
        horizon_hours=config.walk_forward_horizon_hours,
        fee_rate=config.walk_forward_fee_rate,
        slippage_bps=config.walk_forward_slippage_bps,
        funding_rate_8h=config.walk_forward_funding_rate_8h,
    )
    repository.save_strategy_family_walk_forward_report(report)
    append_scratchpad_event(
        run_id=scratchpad_run.run_id,
        event_type=ScratchpadEventType.NOTE,
        payload={"strategy_family_walk_forward_report": report.model_dump(mode="json"), "skipped_cells": skipped},
        task_id=task.task_id,
        thesis_id=task.thesis_id,
        strategy_id=task.strategy_id,
        evidence_refs=[f"strategy_family_walk_forward_report:{report.report_id}"],
        base_dir=config.scratchpad_base_dir,
    )
    severity = ResearchFindingSeverity.LOW if report.passed else ResearchFindingSeverity.MEDIUM
    if report.completed_windows == 0:
        severity = ResearchFindingSeverity.HIGH
    evidence_refs = [
        f"failed_breakout_universe_report:{universe_report.report_id}",
        f"strategy_family_walk_forward_report:{report.report_id}",
    ]
    observations = [
        f"folds={report.folds}",
        f"completed_windows={report.completed_windows}",
        f"passed_windows={report.passed_windows}",
        f"pass_rate={report.pass_rate:.1%}",
        *report.findings,
    ]
    observations.extend(
        (
            f"{window.symbol}:{window.timeframe}:fold={window.fold_index}: "
            f"trades={window.trade_count}, return={window.total_return:.4f}, "
            f"pf={window.profit_factor:.2f}, baseline_return={window.baseline_total_return:.4f}, "
            f"passed={window.passed}"
        )
        for window in report.windows
    )
    return [
        _finding(
            task=task,
            finding_type="strategy_family_walk_forward_test",
            severity=severity,
            summary="Harness ran Failed Breakout strategy-family walk-forward validation.",
            observations=observations,
            evidence_gaps=skipped,
            evidence_refs=evidence_refs,
        )
    ], evidence_refs


def _execute_failed_breakout_monte_carlo(
    repository,
    task: ResearchTask,
    *,
    universe_report: FailedBreakoutUniverseReport,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> tuple[list[ResearchFinding], list[str]]:
    candles_by_cell, skipped = _load_candles_by_cell(
        config,
        symbols=tuple(universe_report.symbols or config.symbols),
        timeframes=tuple(universe_report.timeframes or config.timeframes),
    )
    report = run_failed_breakout_bootstrap_monte_carlo(
        universe_report=universe_report,
        candles_by_cell=candles_by_cell,
        simulations=config.monte_carlo_simulations,
        horizon_trades=config.monte_carlo_horizon_trades,
        seed=config.monte_carlo_seed,
        expensive_simulation_threshold=config.monte_carlo_expensive_threshold,
        approved_to_run=config.approve_expensive_monte_carlo,
        min_sampled_trades=max(10, config.min_trade_count),
        horizon_hours=config.walk_forward_horizon_hours,
        fee_rate=config.walk_forward_fee_rate,
        slippage_bps=config.walk_forward_slippage_bps,
        funding_rate_8h=config.walk_forward_funding_rate_8h,
    )
    repository.save_strategy_family_monte_carlo_report(report)
    append_scratchpad_event(
        run_id=scratchpad_run.run_id,
        event_type=ScratchpadEventType.NOTE,
        payload={"strategy_family_monte_carlo_report": report.model_dump(mode="json"), "skipped_cells": skipped},
        task_id=task.task_id,
        thesis_id=task.thesis_id,
        strategy_id=task.strategy_id,
        evidence_refs=[f"strategy_family_monte_carlo_report:{report.report_id}"],
        base_dir=config.scratchpad_base_dir,
    )
    severity = ResearchFindingSeverity.LOW if report.passed else ResearchFindingSeverity.MEDIUM
    if report.sampled_trade_count == 0 or (report.requires_human_confirmation and not report.approved_to_run):
        severity = ResearchFindingSeverity.HIGH
    evidence_refs = [
        f"failed_breakout_universe_report:{universe_report.report_id}",
        f"strategy_family_monte_carlo_report:{report.report_id}",
    ]
    return [
        _finding(
            task=task,
            finding_type="strategy_family_monte_carlo_test",
            severity=severity,
            summary="Harness ran Failed Breakout strategy-family bootstrap Monte Carlo.",
            observations=[*report.findings],
            evidence_gaps=skipped,
            evidence_refs=evidence_refs,
        )
    ], evidence_refs


def _execute_strategy_monte_carlo(
    repository,
    task: ResearchTask,
    *,
    config: HarnessRunnerConfig,
    scratchpad_run: ResearchScratchpadRun,
) -> tuple[list[ResearchFinding], list[str]]:
    backtest = _backtest_for_task(repository, task)
    if backtest is None:
        return [
            _finding(
                task=task,
                finding_type="monte_carlo_test",
                severity=ResearchFindingSeverity.HIGH,
                summary="Harness could not run strategy Monte Carlo because no source backtest was found.",
                observations=[],
                evidence_gaps=["missing_source_backtest"],
            )
        ], []

    mc_config = MonteCarloBacktestConfig(
        simulations=config.monte_carlo_simulations,
        horizon_trades=config.monte_carlo_horizon_trades,
        seed=config.monte_carlo_seed,
        expensive_simulation_threshold=config.monte_carlo_expensive_threshold,
    )
    trades = repository.query_trades(strategy_id=backtest.strategy_id, limit=5000)
    report = (
        run_trade_bootstrap_monte_carlo(
            backtest,
            trades,
            config=mc_config,
            approved_to_run=config.approve_expensive_monte_carlo,
        )
        if trades
        else run_monte_carlo_backtest(
            backtest,
            config=mc_config,
            approved_to_run=config.approve_expensive_monte_carlo,
        )
    )
    repository.save_monte_carlo_backtest(report)
    append_scratchpad_event(
        run_id=scratchpad_run.run_id,
        event_type=ScratchpadEventType.NOTE,
        payload={"monte_carlo_backtest": report.model_dump(mode="json"), "trade_count": len(trades)},
        task_id=task.task_id,
        thesis_id=task.thesis_id,
        strategy_id=backtest.strategy_id,
        evidence_refs=[f"monte_carlo_backtest:{report.report_id}"],
        base_dir=config.scratchpad_base_dir,
    )
    severity = _monte_carlo_finding_severity(
        median_return=report.median_return,
        p05_return=report.p05_return,
        probability_of_loss=report.probability_of_loss,
        requires_human_confirmation=report.requires_human_confirmation,
        approved_to_run=report.approved_to_run,
    )
    evidence_refs = [f"backtest:{backtest.backtest_id}", f"monte_carlo_backtest:{report.report_id}"]
    return [
        _finding(
            task=task,
            finding_type="monte_carlo_test",
            severity=severity,
            summary="Harness ran strategy-level Monte Carlo path-risk test.",
            observations=[
                f"source_backtest={backtest.backtest_id}",
                f"trades_for_bootstrap={len(trades)}",
                f"median_return={report.median_return:.4f}",
                f"p05_return={report.p05_return:.4f}",
                f"probability_of_loss={report.probability_of_loss:.1%}",
                f"max_drawdown_p05={report.max_drawdown_p05:.4f}",
                *report.notes,
            ],
            evidence_gaps=[] if trades else ["trade_records_unavailable_used_derived_distribution"],
            evidence_refs=evidence_refs,
        )
    ], evidence_refs


def _load_candles_by_cell(
    config: HarnessRunnerConfig,
    *,
    symbols: tuple[str, ...] | None = None,
    timeframes: tuple[str, ...] | None = None,
) -> tuple[dict[tuple[str, str], list], list[str]]:
    candles_by_cell = {}
    skipped = []
    for symbol in symbols or config.symbols:
        for timeframe in timeframes or config.timeframes:
            path = _ohlcv_path(config.data_dir, symbol, timeframe)
            if not path.exists():
                skipped.append(f"{symbol}:{timeframe}:missing_ohlcv")
                continue
            candles = load_freqtrade_ohlcv(path, symbol, timeframe)
            if config.max_candles > 0 and len(candles) > config.max_candles:
                candles = candles[-config.max_candles :]
            candles_by_cell[(symbol, timeframe)] = candles
    return candles_by_cell, skipped


def _trade_regime_observations(
    trades: list[TradeRecord],
    candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]],
) -> tuple[list[str], list[str]]:
    if not trades:
        return [], ["trade_records_unavailable_for_regime_bucket"]
    bucket_returns: dict[str, list[float]] = {}
    missing = 0
    for trade in trades:
        candle_set = _candles_for_trade(trade, candles_by_cell)
        if candle_set is None:
            missing += 1
            continue
        index = _candle_index_at_or_before(candle_set, trade.opened_at)
        if index is None:
            missing += 1
            continue
        regime = _classify_candle_regime(candle_set, index)
        bucket_returns.setdefault(regime, []).append(trade.profit_pct)

    observations = []
    for regime, returns in sorted(bucket_returns.items()):
        wins = [item for item in returns if item > 0]
        losses = [item for item in returns if item < 0]
        total_return = _compound_trade_returns(returns)
        pf = _simple_profit_factor(returns)
        win_rate = len(wins) / len(returns) if returns else 0
        max_dd = _returns_max_drawdown(returns)
        observations.append(
            (
                f"trade_bucket={regime}: trades={len(returns)}, return={total_return:.4f}, "
                f"pf={pf:.2f}, win_rate={win_rate:.1%}, max_drawdown={max_dd:.4f}"
            )
        )
    gaps = []
    if missing:
        gaps.append(f"{missing}_trade_records_could_not_be_matched_to_ohlcv")
    if not observations:
        gaps.append("no_trade_records_bucketed_by_regime")
    return observations, gaps


def _failed_breakout_universe_for_task(repository, task: ResearchTask) -> FailedBreakoutUniverseReport | None:
    report_id = _evidence_ref_id(task.evidence_refs, "failed_breakout_universe_report")
    if report_id is not None:
        return repository.get_failed_breakout_universe_report(report_id)
    if task.thesis_id is not None:
        reports = repository.query_failed_breakout_universe_reports(
            thesis_id=task.thesis_id,
            strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
            limit=1,
        )
        if reports:
            return reports[0]
    reports = repository.query_failed_breakout_universe_reports(
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        limit=1,
    )
    return reports[0] if reports else None


def _backtest_for_task(repository, task: ResearchTask):
    backtest_id = _evidence_ref_id(task.evidence_refs, "backtest")
    if backtest_id is not None:
        backtest = repository.get_backtest(backtest_id)
        if backtest is not None:
            return backtest
    if task.strategy_id is not None:
        backtests = repository.query_backtests(strategy_id=task.strategy_id, limit=1)
        if backtests:
            return backtests[0]
    if task.subject_type == "strategy":
        backtests = repository.query_backtests(strategy_id=task.subject_id, limit=1)
        if backtests:
            return backtests[0]
    return None


def _evidence_ref_id(evidence_refs: list[str], prefix: str) -> str | None:
    marker = f"{prefix}:"
    for ref in evidence_refs:
        if ref.startswith(marker):
            return ref[len(marker) :]
    return None


def _monte_carlo_finding_severity(
    *,
    median_return: float,
    p05_return: float,
    probability_of_loss: float,
    requires_human_confirmation: bool,
    approved_to_run: bool,
) -> ResearchFindingSeverity:
    if requires_human_confirmation and not approved_to_run:
        return ResearchFindingSeverity.HIGH
    if median_return <= 0 or probability_of_loss >= 0.6 or p05_return < -0.2:
        return ResearchFindingSeverity.HIGH
    if probability_of_loss >= 0.45 or p05_return < -0.1:
        return ResearchFindingSeverity.MEDIUM
    return ResearchFindingSeverity.LOW


def _candles_for_trade(
    trade: TradeRecord,
    candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]],
) -> list[OhlcvCandle] | None:
    normalized = _normalize_symbol(trade.symbol)
    candidates = [
        candles
        for (symbol, _), candles in candles_by_cell.items()
        if _normalize_symbol(symbol) == normalized
    ]
    if not candidates:
        candidates = [
            candles
            for (symbol, _), candles in candles_by_cell.items()
            if _normalize_symbol(symbol).startswith(normalized) or normalized.startswith(_normalize_symbol(symbol))
        ]
    if not candidates:
        return None
    return max(candidates, key=len)


def _candle_index_at_or_before(candles: list[OhlcvCandle], timestamp: datetime) -> int | None:
    target = _naive_datetime(timestamp)
    result = None
    for index, candle in enumerate(candles):
        if _naive_datetime(candle.open_time) <= target:
            result = index
        else:
            break
    return result


def _classify_candle_regime(candles: list[OhlcvCandle], index: int) -> str:
    trend = abs(_window_return(candles, index, 48))
    volatility = _window_volatility(candles, index, 48)
    if volatility >= 0.012:
        return "high_volatility"
    if trend >= 0.03:
        return "trend"
    if volatility <= 0.003:
        return "low_volatility"
    return "range"


def _window_return(candles: list[OhlcvCandle], index: int, lookback: int) -> float:
    start = max(0, index - lookback)
    if candles[start].close <= 0:
        return 0
    return candles[index].close / candles[start].close - 1


def _window_volatility(candles: list[OhlcvCandle], index: int, lookback: int) -> float:
    start = max(1, index - lookback + 1)
    returns = [
        candles[offset].close / candles[offset - 1].close - 1
        for offset in range(start, index + 1)
        if candles[offset - 1].close > 0
    ]
    return pstdev(returns) if len(returns) > 1 else 0


def _compound_trade_returns(returns: list[float]) -> float:
    equity = 1.0
    for item in returns:
        equity *= 1 + item
    return equity - 1


def _simple_profit_factor(returns: list[float]) -> float:
    gross_profit = sum(item for item in returns if item > 0)
    gross_loss = abs(sum(item for item in returns if item < 0))
    if gross_loss == 0:
        return 99.0 if gross_profit > 0 else 1.0
    return gross_profit / gross_loss


def _returns_max_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    for item in returns:
        equity *= 1 + item
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    return drawdown


def _normalize_symbol(symbol: str) -> str:
    return symbol.upper().replace(":USDT", "").replace("/", "_").replace(":", "_")


def _naive_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _task_strategy_family(task: ResearchTask) -> StrategyFamily:
    text = " ".join(
        [
            task.subject_id,
            task.hypothesis,
            task.rationale,
            " ".join(task.required_experiments),
        ]
    ).lower()
    for family in StrategyFamily:
        if family.value in text:
            return family
    if "failed breakout" in text or "假突破" in text:
        return StrategyFamily.FAILED_BREAKOUT_PUNISHMENT
    if "funding" in text or "资金费率" in text:
        return StrategyFamily.FUNDING_CROWDING_FADE
    return StrategyFamily.GENERAL_OR_UNKNOWN


def _finding(
    *,
    task: ResearchTask,
    finding_type: str,
    severity: ResearchFindingSeverity,
    summary: str,
    observations: list[str],
    evidence_gaps: list[str],
    evidence_refs: list[str] | None = None,
) -> ResearchFinding:
    return ResearchFinding(
        finding_id=f"finding_{task.task_id}_{uuid4().hex[:8]}",
        thesis_id=task.thesis_id,
        signal_id=task.signal_id or "signal_harness_runner",
        strategy_id=task.strategy_id,
        finding_type=finding_type,
        severity=severity,
        summary=summary,
        observations=observations,
        evidence_gaps=list(dict.fromkeys(evidence_gaps)),
        next_task_ids=[],
        evidence_refs=list(dict.fromkeys([f"research_task:{task.task_id}", *(evidence_refs or [])])),
    )


def _ohlcv_path(data_dir: Path, symbol: str, timeframe: str) -> Path:
    return data_dir / f"{_freqtrade_symbol(symbol)}-{timeframe}-futures.feather"


def _fallback_open_interest_file(data_dir: Path, symbol: str) -> Path | None:
    base = _freqtrade_symbol(symbol)
    candidates = [
        data_dir / f"{base}-5m-open_interest.json",
        data_dir / f"{base}-5m-open_interest.feather",
    ]
    return next((path for path in candidates if path.exists()), None)


def _freqtrade_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")
