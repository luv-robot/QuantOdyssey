from __future__ import annotations

from uuid import uuid4

from app.models import (
    DataSufficiencyLevel,
    EventEpisode,
    ResearchFinding,
    ResearchFindingSeverity,
    ResearchHarnessCycle,
    ResearchTask,
    ResearchTaskType,
    ResearchThesis,
    ReviewSession,
    StrategyFamily,
)
from app.services.harness.budget import apply_harness_budget_guardrails


def build_research_harness_cycle(
    *,
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    review_sessions: list[ReviewSession],
    source: str = "human_research_pipeline",
) -> tuple[ResearchHarnessCycle, list[ResearchFinding], list[ResearchTask]]:
    """Turn review evidence into archived findings and executable next research tasks."""
    findings: list[ResearchFinding] = []
    tasks_by_key: dict[tuple[str, str, str], ResearchTask] = {}

    for session in review_sessions:
        session_tasks = _tasks_for_review_session(thesis, event_episode, session)
        for task in session_tasks:
            tasks_by_key[(task.task_type.value, task.subject_type, task.subject_id)] = task
        finding = _finding_for_review_session(
            thesis=thesis,
            event_episode=event_episode,
            session=session,
            next_task_ids=[task.task_id for task in session_tasks],
        )
        findings.append(finding)

    if not review_sessions:
        task = _data_sufficiency_task(thesis, event_episode, None)
        tasks_by_key[(task.task_type.value, task.subject_type, task.subject_id)] = task
        findings.append(
            ResearchFinding(
                finding_id=f"finding_{event_episode.signal_id}_{uuid4().hex[:8]}",
                thesis_id=thesis.thesis_id,
                signal_id=event_episode.signal_id,
                strategy_id=None,
                finding_type="pipeline_gap",
                severity=ResearchFindingSeverity.MEDIUM,
                summary="Research pipeline produced no ReviewSession, so Harness generated a diagnostic task.",
                observations=["No candidate reached the ReviewSession stage."],
                evidence_gaps=["review_session_missing"],
                next_task_ids=[task.task_id],
                evidence_refs=[f"event_episode:{event_episode.event_id}"],
            )
        )

    tasks, _budget_decisions = apply_harness_budget_guardrails(list(tasks_by_key.values()))
    for index, finding in enumerate(findings):
        if not finding.next_task_ids:
            findings[index] = finding.model_copy(update={"next_task_ids": [task.task_id for task in tasks]})

    cycle = ResearchHarnessCycle(
        cycle_id=f"harness_cycle_{event_episode.signal_id}_{uuid4().hex[:8]}",
        thesis_id=thesis.thesis_id,
        signal_id=event_episode.signal_id,
        source=source,
        finding_ids=[finding.finding_id for finding in findings],
        task_ids=[task.task_id for task in tasks],
        summary=_cycle_summary(event_episode, findings, tasks),
    )
    return cycle, findings, tasks


def _finding_for_review_session(
    *,
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    session: ReviewSession,
    next_task_ids: list[str],
) -> ResearchFinding:
    scorecard = session.scorecard
    maturity = session.maturity_score
    observations = [
        f"validation_data_sufficiency_level={scorecard.get('validation_data_sufficiency_level')}",
        f"profit_factor={scorecard.get('profit_factor')}",
        f"sharpe={scorecard.get('sharpe')}",
        f"total_return={scorecard.get('total_return')}",
        f"trades={scorecard.get('trades')}",
        f"best_baseline={scorecard.get('best_baseline')}",
        f"outperformed_best_baseline={scorecard.get('outperformed_best_baseline')}",
        f"robustness_score={scorecard.get('robustness_score')}",
        f"maturity_stage={maturity.stage}",
    ]
    event_count = event_episode.features.get("event_count")
    trigger_count = event_episode.features.get("trigger_count")
    if event_count is not None:
        observations.append(f"event_count={event_count}")
    if trigger_count is not None:
        observations.append(f"trigger_count={trigger_count}")
    for blocker in maturity.blockers:
        observations.append(f"blocker={blocker}")

    evidence_gaps = list(dict.fromkeys([*event_episode.missing_evidence, *[claim.statement for claim in session.blind_spots]]))
    severity = ResearchFindingSeverity.HIGH if session.evidence_against else ResearchFindingSeverity.MEDIUM
    summary = (
        "Reviewed strategy variant is not ready for promotion; Harness generated follow-up research tasks."
        if session.evidence_against
        else "Reviewed strategy variant has supportive evidence but still needs follow-up validation."
    )
    return ResearchFinding(
        finding_id=f"finding_{session.strategy_id}_{uuid4().hex[:8]}",
        thesis_id=thesis.thesis_id,
        signal_id=session.signal_id,
        strategy_id=session.strategy_id,
        finding_type="review_session_analysis",
        severity=severity,
        summary=summary,
        observations=observations,
        evidence_gaps=evidence_gaps,
        next_task_ids=next_task_ids,
        evidence_refs=[
            f"review_session:{session.session_id}",
            f"event_episode:{event_episode.event_id}",
        ],
    )


def _tasks_for_review_session(
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    session: ReviewSession,
) -> list[ResearchTask]:
    tasks: list[ResearchTask] = []
    scorecard = session.scorecard
    baseline_failed = scorecard.get("outperformed_best_baseline") is False
    robustness_score = float(scorecard.get("robustness_score") or 0)
    event_count = int(event_episode.features.get("event_count") or 0)
    trigger_count = int(event_episode.features.get("trigger_count") or 0)

    if event_episode.missing_evidence or session.blind_spots:
        tasks.append(_data_sufficiency_task(thesis, event_episode, session))

    if event_episode.strategy_family == StrategyFamily.FUNDING_CROWDING_FADE:
        tasks.append(_funding_event_definition_task(thesis, event_episode, session))
        tasks.append(_funding_parameter_sensitivity_task(thesis, event_episode, session))

    if baseline_failed:
        tasks.append(
            _task(
                task_type=ResearchTaskType.BASELINE_TEST,
                thesis=thesis,
                event_episode=event_episode,
                session=session,
                subject_type="strategy",
                subject_id=session.strategy_id,
                hypothesis="The current strategy should only continue if it beats matched event baselines, not only proxy or narrative baselines.",
                rationale="ReviewSession reported that the strategy did not outperform the best matched baseline.",
                required_experiments=[
                    "rerun matched event-level baselines over the same timerange",
                    "compare funding-only, funding-plus-OI, failed-breakout-only, opposite-direction, and cash baselines",
                ],
                success_metrics=["strategy_total_return > best_baseline_return", "profit_factor > best_baseline_profit_factor"],
                failure_conditions=["cash remains the best baseline", "strategy underperforms funding_plus_oi_event"],
                priority_score=82,
                estimated_cost=25,
            )
        )

    if robustness_score < 60:
        tasks.append(
            _task(
                task_type=ResearchTaskType.REGIME_BUCKET_TEST,
                thesis=thesis,
                event_episode=event_episode,
                session=session,
                subject_type="strategy",
                subject_id=session.strategy_id,
                hypothesis="Failure may cluster in specific market regimes rather than across all funding-crowding events.",
                rationale=f"Robustness score is {robustness_score:.2f}, below the current research threshold.",
                required_experiments=[
                    "bucket trades by trend/range/volatility regime",
                    "compare PF, Sharpe, drawdown, and hit rate per regime",
                ],
                success_metrics=["at least one predeclared regime bucket shows stable PF > 1.2", "regime rule reduces drawdown without collapsing sample count"],
                failure_conditions=["all regime buckets remain below PF 1.0", "filtered sample count becomes too low"],
                priority_score=78,
                estimated_cost=35,
            )
        )
        tasks.append(
            _task(
                task_type=ResearchTaskType.MONTE_CARLO_TEST,
                thesis=thesis,
                event_episode=event_episode,
                session=session,
                subject_type="strategy",
                subject_id=session.strategy_id,
                hypothesis="Trade-path risk may remain unacceptable even if the event definition is tightened.",
                rationale="ReviewSession and robustness checks indicate negative or fragile bootstrap behavior.",
                required_experiments=["run trade-level bootstrap on tightened event definitions", "compare median return, p05 return, and loss probability"],
                success_metrics=["median_return > 0", "probability_of_loss < 0.45", "p05_return is within accepted loss budget"],
                failure_conditions=["median_return <= 0", "loss_probability remains high"],
                priority_score=70,
                estimated_cost=50,
            )
        )

    if event_count == 0 or trigger_count == 0:
        tasks.append(
            _task(
                task_type=ResearchTaskType.EVENT_FREQUENCY_SCAN,
                thesis=thesis,
                event_episode=event_episode,
                session=session,
                subject_type="strategy_family",
                subject_id=event_episode.strategy_family.value,
                hypothesis="The current Funding Crowding Fade definition may be too narrow or the latest signal may not represent a true event.",
                rationale=f"Current signal produced event_count={event_count} and trigger_count={trigger_count}.",
                required_experiments=[
                    "scan BTC/ETH/SOL 5m and 15m for funding+OI+failed-breakout events",
                    "report event frequency before generating more strategy variants",
                ],
                success_metrics=["event_count >= 200 over the research universe", "trigger_count >= 80 over the research universe"],
                failure_conditions=["event frequency remains too low", "events cluster in one symbol only"],
                priority_score=88,
                estimated_cost=30,
            )
        )
    if not baseline_failed and robustness_score >= 60:
        tasks.append(
            _task(
                task_type=ResearchTaskType.WATCHLIST_REVIEW,
                thesis=thesis,
                event_episode=event_episode,
                session=session,
                subject_type="strategy",
                subject_id=session.strategy_id,
                hypothesis="A supported variant should enter research watchlist review before any paper promotion.",
                rationale="The strategy beat its matched baseline and current robustness score is above the review threshold.",
                required_experiments=[
                    "summarize remaining ReviewSession questions",
                    "confirm paper-trading prerequisites and data coverage",
                    "record why this variant is materially different from prior failures",
                ],
                success_metrics=["watchlist rationale is explicit", "paper prerequisites are identified"],
                failure_conditions=["unresolved review questions block promotion", "strategy is too similar to prior failed variants"],
                priority_score=72,
                estimated_cost=15,
            )
        )
    return tasks


def _funding_event_definition_task(
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    session: ReviewSession,
) -> ResearchTask:
    return _task(
        task_type=ResearchTaskType.EVENT_DEFINITION_TEST,
        thesis=thesis,
        event_episode=event_episode,
        session=session,
        subject_type="strategy_family",
        subject_id=event_episode.strategy_family.value,
        hypothesis="Funding Crowding Fade may only have value when funding extreme, high OI, failed breakout, and OI retreat occur together.",
        rationale="The latest signal had historical OI available, but the event quality was weak and the strategy did not beat cash.",
        required_experiments=[
            "test funding_percentile thresholds 90/95/97.5",
            "test OI_percentile thresholds 75/85/90",
            "test failed-breakout windows 3/6/12 bars",
            "test OI retreat confirmation none/0.5%/1%/2%",
        ],
        success_metrics=["stable neighborhood beats cash and funding_extreme_only_event", "sample count remains above minimum"],
        failure_conditions=["only one isolated parameter cell works", "strict event definitions collapse sample count"],
        priority_score=92,
        estimated_cost=40,
    )


def _funding_parameter_sensitivity_task(
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    session: ReviewSession,
) -> ResearchTask:
    return _task(
        task_type=ResearchTaskType.PARAMETER_SENSITIVITY_TEST,
        thesis=thesis,
        event_episode=event_episode,
        session=session,
        subject_type="strategy_family",
        subject_id=event_episode.strategy_family.value,
        hypothesis="Declared parameter ranges should show robust regions; isolated best cells should be treated as overfitting risk.",
        rationale="Optimizer/hyperopt is not yet part of the pipeline; Harness should schedule a bounded sensitivity run before any promotion.",
        required_experiments=[
            "run declared grid only, not open-ended hyperopt",
            "record search budget and failed variants",
            "compare neighboring parameter cells instead of selecting the single best run",
        ],
        success_metrics=["multiple adjacent cells retain PF > 1.1", "Sharpe and drawdown do not collapse under perturbation"],
        failure_conditions=["best result is isolated", "search budget is high relative to evidence quality"],
        priority_score=80,
        estimated_cost=200,
        approval_required=True,
        autonomy_level=1,
    )


def _data_sufficiency_task(
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    session: ReviewSession | None,
) -> ResearchTask:
    missing = list(event_episode.missing_evidence)
    if session is not None:
        missing.extend(claim.statement for claim in session.blind_spots)
    missing = list(dict.fromkeys(missing))
    return _task(
        task_type=ResearchTaskType.DATA_SUFFICIENCY_REVIEW,
        thesis=thesis,
        event_episode=event_episode,
        session=session,
        subject_type="strategy_family",
        subject_id=event_episode.strategy_family.value,
        hypothesis="The next experiment should not proceed until the evidence gap is resolved or explicitly accepted.",
        rationale="Harness found missing or weak evidence in the current review artifacts.",
        required_experiments=missing or ["inspect data sufficiency artifacts"],
        success_metrics=["missing_evidence is empty or explicitly accepted", "ReviewSession blind_spots no longer include data-source gaps"],
        failure_conditions=["strategy conclusion depends on unavailable evidence"],
        priority_score=85,
        estimated_cost=20,
    )


def _task(
    *,
    task_type: ResearchTaskType,
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    session: ReviewSession | None,
    subject_type: str,
    subject_id: str,
    hypothesis: str,
    rationale: str,
    required_experiments: list[str],
    success_metrics: list[str],
    failure_conditions: list[str],
    priority_score: float,
    estimated_cost: int,
    approval_required: bool = False,
    autonomy_level: int = 2,
) -> ResearchTask:
    task_id = f"task_{task_type.value}_{subject_id}_{uuid4().hex[:8]}"
    evidence_refs = [f"event_episode:{event_episode.event_id}"]
    if session is not None:
        evidence_refs.append(f"review_session:{session.session_id}")
    return ResearchTask(
        task_id=task_id,
        task_type=task_type,
        subject_type=subject_type,
        subject_id=subject_id,
        thesis_id=thesis.thesis_id,
        signal_id=event_episode.signal_id,
        strategy_id=None if session is None else session.strategy_id,
        hypothesis=hypothesis,
        rationale=rationale,
        required_experiments=required_experiments,
        success_metrics=success_metrics,
        failure_conditions=failure_conditions,
        required_data_level=event_episode.validation_data_sufficiency_level,
        estimated_cost=estimated_cost,
        priority_score=priority_score,
        approval_required=approval_required,
        autonomy_level=autonomy_level,
        evidence_refs=evidence_refs,
    )


def _cycle_summary(
    event_episode: EventEpisode,
    findings: list[ResearchFinding],
    tasks: list[ResearchTask],
) -> str:
    high_findings = sum(1 for finding in findings if finding.severity == ResearchFindingSeverity.HIGH)
    approval_tasks = sum(1 for task in tasks if task.approval_required)
    return (
        f"Harness generated {len(findings)} finding(s) and {len(tasks)} next task(s) for "
        f"{event_episode.strategy_family.value}; {high_findings} high-severity finding(s), "
        f"{approval_tasks} task(s) require human approval."
    )
