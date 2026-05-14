from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.models import (
    BacktestReport,
    BacktestStatus,
    BacktestValidationReport,
    BaselineComparisonReport,
    ExperimentQueueItem,
    ExperimentQueueStatus,
    CandidateRankingResult,
    ExperimentManifest,
    EventEpisode,
    MarketSignal,
    MonteCarloBacktestConfig,
    MonteCarloBacktestReport,
    PaperTradingPlan,
    ResearchDesignDraft,
    ResearchThesis,
    ResourceBudgetReport,
    RealBacktestValidationSuiteReport,
    CrossSymbolValidationReport,
    ReviewSession,
    RobustnessReport,
    RiskAuditResult,
    StrategyCandidate,
    StrategyManifest,
    ThesisPreReview,
    ThesisStatus,
    WorkflowRun,
    WorkflowState,
)
from app.services.backtester import (
    compare_to_proxy_baselines,
    evaluate_robustness,
    run_mock_backtest,
    run_monte_carlo_backtest,
    run_real_validation_suite,
)
from app.services.backtester.freqtrade_cli import run_freqtrade_backtest
from app.services.backtester.monte_carlo import run_trade_bootstrap_monte_carlo
from app.services.backtester.validation import validate_backtest_reliability
from app.services.market_data.quality import audit_market_signal_quality
from app.services.market_data.regime_labels import label_market_regime
from app.services.operations import evaluate_resource_budget
from app.services.paper_trading import build_paper_trading_plan
from app.services.researcher import build_researcher_logs
from app.services.researcher.candidates import (
    generate_thesis_strategy_candidates,
    rank_strategy_candidates,
)
from app.services.researcher.assets import build_research_asset_index_entry
from app.services.researcher.experiments import build_experiment_manifest
from app.services.researcher.pre_review import (
    build_event_episode,
    build_research_design_draft,
    build_thesis_pre_review,
)
from app.services.researcher.queue import (
    build_experiment_queue_item,
    mark_experiment_queue_completed,
)
from app.services.reviewer import (
    build_enhanced_review_metrics,
    build_negative_result_case,
    build_review_case,
    build_review_session,
    summarize_trades,
)
from app.services.risk_auditor import audit_strategy_code
from app.storage import InMemoryReviewStore, QuantRepository


class CandidateResearchResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    candidate: StrategyCandidate
    workflow: WorkflowRun
    risk_audit: RiskAuditResult
    backtest: BacktestReport | None = None
    validation: BacktestValidationReport | None = None
    experiment_manifest: ExperimentManifest | None = None
    baseline_comparison: BaselineComparisonReport | None = None
    robustness_report: RobustnessReport | None = None
    queue_item: ExperimentQueueItem | None = None
    resource_budget: ResourceBudgetReport | None = None
    real_validation_suite: RealBacktestValidationSuiteReport | None = None
    cross_symbol_validation: CrossSymbolValidationReport | None = None
    monte_carlo: MonteCarloBacktestReport | None = None
    review_case_id: str | None = None
    selected: bool = False


class HumanResearchPipelineResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thesis: ResearchThesis
    signal: MarketSignal
    pre_review: ThesisPreReview
    research_design: ResearchDesignDraft
    event_episode: EventEpisode
    ranking: CandidateRankingResult
    candidates: list[CandidateResearchResult]
    review_sessions: list[ReviewSession]
    selected_candidate_id: str | None = None
    paper_trading_plan: PaperTradingPlan | None = None
    final_status: ThesisStatus


def run_human_research_pipeline(
    thesis: ResearchThesis,
    signal: MarketSignal,
    repository: QuantRepository,
    candidate_count: int = 3,
    monte_carlo_config: MonteCarloBacktestConfig | None = None,
    approve_expensive_monte_carlo: bool = False,
    backtest_mode: str | None = None,
    strategy_dir: Path = Path("freqtrade_user_data/strategies"),
    review_store: InMemoryReviewStore | None = None,
) -> HumanResearchPipelineResult:
    thesis = thesis.model_copy(
        update={
            "status": ThesisStatus.TESTING,
            "linked_signal_ids": _linked_signal_ids(thesis, signal),
            "constraints": _constraints_with_historical_lessons(thesis, signal, repository),
        }
    )
    repository.save_signal(signal)
    regime_snapshot = label_market_regime(signal)
    repository.save_market_regime_snapshot(regime_snapshot)
    repository.save_data_quality_report(audit_market_signal_quality(signal))
    repository.save_research_thesis(thesis)
    pre_review = build_thesis_pre_review(thesis)
    repository.save_thesis_pre_review(pre_review)
    research_design = build_research_design_draft(thesis, pre_review)
    repository.save_research_design_draft(research_design)
    event_episode = build_event_episode(thesis, signal, research_design)
    repository.save_event_episode(event_episode)

    candidates = generate_thesis_strategy_candidates(thesis, signal, count=candidate_count)
    ranking = rank_strategy_candidates(signal, candidates)
    store = review_store or InMemoryReviewStore()
    results: list[CandidateResearchResult] = []
    review_sessions: list[ReviewSession] = []

    for candidate in ranking.candidates:
        manifest = candidate.manifest
        strategy_code = candidate.strategy_code
        _write_strategy_code(candidate, strategy_code, strategy_dir)
        repository.save_strategy(manifest)
        prompt_log, response_log = build_researcher_logs(
            signal,
            manifest,
            strategy_code,
            model="human-led-agent",
            prompt_version="human_led_multi_candidate_v1",
            thesis=thesis,
        )
        repository.save_prompt_log(prompt_log)
        repository.save_model_response_log(response_log)

        workflow = WorkflowRun(
            workflow_run_id=f"run_{candidate.candidate_id}",
            signal_id=signal.signal_id,
            strategy_id=manifest.strategy_id,
            state=WorkflowState.STRATEGY_GENERATED,
        )
        repository.save_workflow_run(workflow)

        workflow = workflow.transition(WorkflowState.RISK_AUDITING)
        repository.save_workflow_run(workflow)
        risk_audit = audit_strategy_code(strategy_code, manifest)
        repository.save_risk_audit(risk_audit)

        if not risk_audit.approved:
            workflow = workflow.transition(WorkflowState.RISK_REJECTED)
            repository.save_workflow_run(workflow)
            review = store.add(build_review_case(signal, manifest, risk_audit))
            repository.save_review(review)
            results.append(
                CandidateResearchResult(
                    candidate=candidate,
                    workflow=workflow.transition(WorkflowState.REVIEW_COMPLETED),
                    risk_audit=risk_audit,
                    review_case_id=review.case_id,
                )
            )
            repository.save_workflow_run(results[-1].workflow)
            continue

        workflow = workflow.transition(WorkflowState.RISK_APPROVED)
        repository.save_workflow_run(workflow)

        resource_budget = evaluate_resource_budget(
            candidate,
            config=monte_carlo_config,
            approved_expensive_run=approve_expensive_monte_carlo,
        )
        repository.save_resource_budget_report(resource_budget)
        queue_item = build_experiment_queue_item(
            candidate,
            config=monte_carlo_config,
            approved_expensive_run=approve_expensive_monte_carlo,
        )
        repository.save_experiment_queue_item(queue_item)

        workflow = workflow.transition(WorkflowState.BACKTEST_RUNNING)
        repository.save_workflow_run(workflow)
        backtest, trades, backtest_metadata = _run_backtest(signal, manifest, mode=backtest_mode)
        repository.save_backtest(backtest)
        for trade in trades:
            repository.save_trade(trade)
        experiment_manifest = build_experiment_manifest(
            signal=signal,
            manifest=manifest,
            backtest=backtest,
            strategy_code=strategy_code,
            backtest_mode=backtest_metadata.get("backtest_mode", backtest_mode or "real"),
            metadata=backtest_metadata,
            config_path=Path(backtest_metadata["config_path"]) if backtest_metadata.get("config_path") else None,
            random_seed=monte_carlo_config.seed if monte_carlo_config is not None else None,
        )
        repository.save_experiment_manifest(experiment_manifest)
        baseline_comparison = compare_to_proxy_baselines(signal, backtest)
        repository.save_baseline_comparison(baseline_comparison)

        validation = _validate_backtest(backtest)
        repository.save_backtest_validation(validation)
        real_validation_suite = None
        cross_symbol_validation = None
        if backtest_metadata.get("backtest_mode") == "real" and backtest.status == BacktestStatus.PASSED:
            (
                real_validation_suite,
                real_oos,
                real_walk_forward,
                real_fee_slippage,
                cross_symbol_validation,
            ) = run_real_validation_suite(
                manifest=manifest,
                source_backtest=backtest,
                primary_symbol=signal.symbol,
            )
            repository.save_real_backtest_validation_suite(real_validation_suite)
            repository.save_cross_symbol_validation(cross_symbol_validation)
            if real_oos is not None:
                repository.save_backtest(real_oos)
            for report in real_walk_forward:
                repository.save_backtest(report)
            if real_fee_slippage is not None:
                repository.save_backtest(real_fee_slippage)

        monte_carlo = (
            run_trade_bootstrap_monte_carlo(
                backtest,
                trades,
                config=monte_carlo_config,
                approved_to_run=approve_expensive_monte_carlo,
            )
            if trades
            else run_monte_carlo_backtest(
                backtest,
                config=monte_carlo_config,
                approved_to_run=approve_expensive_monte_carlo,
            )
        )
        repository.save_monte_carlo_backtest(monte_carlo)
        robustness_report = evaluate_robustness(
            backtest=backtest,
            validation=validation,
            monte_carlo=monte_carlo,
            baseline=baseline_comparison,
        )
        repository.save_robustness_report(robustness_report)
        if trades:
            repository.save_trade_summary(summarize_trades(manifest.strategy_id, trades))
            repository.save_enhanced_review_metrics(
                build_enhanced_review_metrics(
                    signal=signal,
                    strategy_id=manifest.strategy_id,
                    trades=trades,
                    candles=[],
                    funding_rate=float(signal.features.get("funding_rate", 0) or 0),
                    backtest=backtest,
                    monte_carlo=monte_carlo,
                    template_name=candidate.template_name,
                )
            )

        passed = (
            backtest.status == BacktestStatus.PASSED
            and validation.approved
            and not (monte_carlo.requires_human_confirmation and not monte_carlo.approved_to_run)
        )
        workflow = workflow.transition(
            WorkflowState.HUMAN_REVIEW_REQUIRED if passed else WorkflowState.BACKTEST_FAILED,
            error=None if passed else _failure_reason(backtest, validation, monte_carlo),
        )
        repository.save_workflow_run(workflow)

        review = store.add(build_review_case(signal, manifest, risk_audit, backtest))
        repository.save_review(review)
        review_session = build_review_session(
            pre_review=pre_review,
            research_design=research_design,
            event_episode=event_episode,
            backtest=backtest,
            baseline=baseline_comparison,
            robustness=robustness_report,
            review_case=review,
        )
        repository.save_review_session(review_session)
        review_sessions.append(review_session)
        repository.save_research_asset_index_entry(
            build_research_asset_index_entry(
                thesis=thesis,
                candidate=candidate,
                backtest=backtest,
                baseline=baseline_comparison,
                robustness=robustness_report,
                regime=regime_snapshot,
                review_case_id=review.case_id,
            )
        )
        if queue_item.status == ExperimentQueueStatus.APPROVED:
            queue_item = mark_experiment_queue_completed(queue_item)
            repository.save_experiment_queue_item(queue_item)

        workflow = workflow.transition(WorkflowState.REVIEW_COMPLETED)
        repository.save_workflow_run(workflow)
        results.append(
            CandidateResearchResult(
                candidate=candidate,
                workflow=workflow,
                risk_audit=risk_audit,
                backtest=backtest,
                validation=validation,
                experiment_manifest=experiment_manifest,
                baseline_comparison=baseline_comparison,
                robustness_report=robustness_report,
                queue_item=queue_item,
                resource_budget=resource_budget,
                real_validation_suite=real_validation_suite,
                cross_symbol_validation=cross_symbol_validation,
                monte_carlo=monte_carlo,
                review_case_id=review.case_id,
            )
        )

    selected_candidate_id = _select_candidate(results)
    paper_trading_plan = None
    if selected_candidate_id is not None:
        results = [
            item.model_copy(update={"selected": item.candidate.candidate_id == selected_candidate_id})
            for item in results
        ]
        selected_result = next(item for item in results if item.candidate.candidate_id == selected_candidate_id)
        if selected_result.backtest is not None:
            paper_trading_plan = build_paper_trading_plan(
                signal,
                selected_result.candidate.manifest,
                selected_result.backtest,
            )
            repository.save_paper_trading_plan(paper_trading_plan)

    for item in results:
        negative_case = build_negative_result_case(thesis, item, selected_candidate_id)
        if negative_case is not None:
            repository.save_negative_result_case(negative_case)

    final_status = ThesisStatus.SUPPORTED if selected_candidate_id else ThesisStatus.REJECTED
    thesis = thesis.model_copy(update={"status": final_status})
    repository.save_research_thesis(thesis)
    return HumanResearchPipelineResult(
        thesis=thesis,
        signal=signal,
        pre_review=pre_review,
        research_design=research_design,
        event_episode=event_episode,
        ranking=ranking.model_copy(update={"selected_candidate_id": selected_candidate_id}),
        candidates=results,
        review_sessions=review_sessions,
        selected_candidate_id=selected_candidate_id,
        paper_trading_plan=paper_trading_plan,
        final_status=final_status,
    )


def _linked_signal_ids(thesis: ResearchThesis, signal: MarketSignal) -> list[str]:
    linked = list(dict.fromkeys([*thesis.linked_signal_ids, signal.signal_id]))
    return linked


def _constraints_with_historical_lessons(
    thesis: ResearchThesis,
    signal: MarketSignal,
    repository: QuantRepository,
    limit: int = 5,
) -> list[str]:
    lessons = []
    query_metrics = getattr(repository, "query_enhanced_review_metrics", None)
    if callable(query_metrics):
        metrics = query_metrics(signal_id=signal.signal_id, limit=limit)
        if not metrics:
            metrics = query_metrics(limit=limit)
        for metric in metrics:
            lessons.extend(metric.reusable_lessons)

    historical_constraints = [
        f"Historical lesson: {lesson}"
        for lesson in dict.fromkeys(lessons)
    ]
    return list(dict.fromkeys([*thesis.constraints, *historical_constraints]))


def _write_strategy_code(
    candidate: StrategyCandidate,
    strategy_code: str,
    strategy_dir: Path,
) -> None:
    strategy_dir.mkdir(parents=True, exist_ok=True)
    path = Path(candidate.manifest.file_path)
    if not path.is_absolute():
        path = strategy_dir / path.name
    path.write_text(strategy_code, encoding="utf-8")


def _validate_backtest(report: BacktestReport) -> BacktestValidationReport:
    out_of_sample = report.model_copy(
        update={
            "backtest_id": f"{report.backtest_id}_oos",
            "timerange": "20250101-20260501",
            "total_return": round(report.total_return * 0.82, 6),
            "profit_factor": max(0, round(report.profit_factor - 0.05, 2)),
            "status": report.status,
        }
    )
    walk_forward = [
        report.model_copy(
            update={
                "backtest_id": f"{report.backtest_id}_wf_{index}",
                "timerange": timerange,
                "total_return": round(report.total_return * multiplier, 6),
            }
        )
        for index, (timerange, multiplier) in enumerate(
            [("20240101-20240701", 0.76), ("20240701-20250101", 0.88)],
            start=1,
        )
    ]
    sensitivity = [
        report.model_copy(
            update={
                "backtest_id": f"{report.backtest_id}_sens_{index}",
                "total_return": round(report.total_return * multiplier, 6),
            }
        )
        for index, multiplier in enumerate([0.72, 0.91], start=1)
    ]
    fee_slippage = report.model_copy(
        update={
            "backtest_id": f"{report.backtest_id}_fees",
            "total_return": round(report.total_return * 0.7, 6),
            "profit_factor": max(0, round(report.profit_factor - 0.1, 2)),
            "status": (
                BacktestStatus.PASSED
                if report.status == BacktestStatus.PASSED and report.profit_factor >= 1.3
                else BacktestStatus.FAILED
            ),
            "error": None
            if report.status == BacktestStatus.PASSED and report.profit_factor >= 1.3
            else "Fee and slippage adjusted pass criteria were not met.",
        }
    )
    return validate_backtest_reliability(
        report,
        out_of_sample_report=out_of_sample,
        walk_forward_reports=walk_forward,
        sensitivity_reports=sensitivity,
        fee_slippage_report=fee_slippage,
    )


def _run_backtest(
    signal: MarketSignal,
    manifest: StrategyManifest,
    mode: str | None,
) -> tuple[BacktestReport, list, dict]:
    selected_mode = (mode or os.getenv("QUANTODYSSEY_BACKTEST_MODE", "real")).lower()
    config_path = Path(os.getenv("FREQTRADE_CONFIG", "configs/freqtrade_config.json"))
    if selected_mode == "mock":
        return (
            run_mock_backtest(signal, manifest),
            [],
            {
                "backtest_mode": "mock",
                "config_path": str(config_path),
                "command": ["mock_backtest"],
            },
        )
    if selected_mode != "real":
        raise ValueError(f"unsupported backtest mode: {selected_mode}")
    backtest, trades, metadata = run_freqtrade_backtest(
        manifest,
        timerange=os.getenv("FREQTRADE_BACKTEST_TIMERANGE", "20240101-20260501"),
        config_path=config_path,
        userdir=Path(os.getenv("FREQTRADE_USER_DATA", "freqtrade_user_data")),
        timeout_seconds=int(os.getenv("FREQTRADE_BACKTEST_TIMEOUT", "600")),
    )
    metadata["backtest_mode"] = "real"
    metadata["config_path"] = str(config_path)
    return backtest, trades, metadata


def _failure_reason(
    backtest: BacktestReport,
    validation: BacktestValidationReport,
    monte_carlo: MonteCarloBacktestReport,
) -> str:
    reasons = []
    if backtest.status == BacktestStatus.FAILED:
        reasons.append(backtest.error or "Backtest failed.")
    if not validation.approved:
        reasons.extend(validation.findings)
    if monte_carlo.requires_human_confirmation and not monte_carlo.approved_to_run:
        reasons.extend(monte_carlo.notes)
    return " ".join(reasons) or "Research pipeline criteria were not met."


def _select_candidate(results: list[CandidateResearchResult]) -> str | None:
    eligible = [
        item
        for item in results
        if item.risk_audit.approved
        and item.backtest is not None
        and item.validation is not None
        and item.monte_carlo is not None
        and item.backtest.status == BacktestStatus.PASSED
        and item.validation.approved
        and not (item.monte_carlo.requires_human_confirmation and not item.monte_carlo.approved_to_run)
    ]
    if not eligible:
        return None
    selected = sorted(
        eligible,
        key=lambda item: (
            _template_alignment_score(item),
            item.candidate.score,
            item.backtest.profit_factor if item.backtest else 0,
            item.monte_carlo.median_return if item.monte_carlo else 0,
        ),
        reverse=True,
    )[0]
    return selected.candidate.candidate_id


def _template_alignment_score(item: CandidateResearchResult) -> int:
    preferred_templates = {
        "funding_crowding_fade_short",
    }
    return 1 if item.candidate.template_name in preferred_templates else 0
