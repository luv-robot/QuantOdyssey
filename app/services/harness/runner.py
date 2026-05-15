from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.models import (
    DataSufficiencyLevel,
    ResearchFinding,
    ResearchFindingSeverity,
    ResearchScratchpadRun,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    ScratchpadEventType,
    StrategyFamily,
)
from app.services.harness.event_definition import (
    build_event_definition_universe_report,
    build_failed_breakout_universe_report,
    run_failed_breakout_event_definition_sensitivity,
    run_funding_crowding_event_definition_sensitivity,
)
from app.services.harness.scratchpad import append_scratchpad_event, create_scratchpad_run
from app.services.harness.screening import (
    build_baseline_implied_regime_report,
    build_strategy_family_baseline_board,
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
}


@dataclass(frozen=True)
class HarnessRunnerConfig:
    data_dir: Path = Path("freqtrade_user_data/data/binance/futures")
    symbols: tuple[str, ...] = ("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT")
    timeframes: tuple[str, ...] = ("5m", "15m")
    max_tasks: int = 5
    max_candles: int = 5000
    max_trials: int = 80
    min_trade_count: int = 20
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
        limit=config.max_tasks,
    )
    results: list[HarnessTaskRunResult] = []
    for task in proposed_tasks:
        result = _run_one_task(repository, task, config=config, scratchpad_run=scratchpad_run)
        results.append(result)

    executed = sum(1 for result in results if result.skipped_reason is None)
    completed = sum(1 for result in results if result.status == ResearchTaskStatus.COMPLETED)
    blocked = sum(1 for result in results if result.status == ResearchTaskStatus.BLOCKED)
    summary = HarnessQueueRunSummary(
        run_id=run_id,
        considered=len(proposed_tasks),
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
    regime = build_baseline_implied_regime_report(board)
    append_scratchpad_event(
        run_id=scratchpad_run.run_id,
        event_type=ScratchpadEventType.NOTE,
        payload={
            "baseline_board": board.model_dump(mode="json"),
            "baseline_implied_regime": regime.model_dump(mode="json"),
            "skipped_cells": skipped,
        },
        task_id=task.task_id,
        thesis_id=task.thesis_id,
        strategy_id=task.strategy_id,
        evidence_refs=[f"research_task:{task.task_id}"],
        base_dir=config.scratchpad_base_dir,
    )
    rows = [
        f"{row.strategy_family}: return={row.total_return:.4f}, pf={row.profit_factor:.4f}, trades={row.trades}"
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
                *rows,
            ],
            evidence_gaps=skipped,
            evidence_refs=[
                f"scratchpad:{scratchpad_run.run_id}:strategy_family_baseline_board:{board.board_id}",
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


def _load_candles_by_cell(
    config: HarnessRunnerConfig,
) -> tuple[dict[tuple[str, str], list], list[str]]:
    candles_by_cell = {}
    skipped = []
    for symbol in config.symbols:
        for timeframe in config.timeframes:
            path = _ohlcv_path(config.data_dir, symbol, timeframe)
            if not path.exists():
                skipped.append(f"{symbol}:{timeframe}:missing_ohlcv")
                continue
            candles = load_freqtrade_ohlcv(path, symbol, timeframe)
            if config.max_candles > 0 and len(candles) > config.max_candles:
                candles = candles[-config.max_candles :]
            candles_by_cell[(symbol, timeframe)] = candles
    return candles_by_cell, skipped


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
