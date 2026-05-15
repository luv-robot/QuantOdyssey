from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.models import (
    EvaluationType,
    EventEpisode,
    PreReviewStatus,
    ResearchDesignDraft,
    ResearchFinding,
    ResearchFindingSeverity,
    ResearchHarnessCycle,
    ResearchScratchpadRun,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    ResearchThesis,
    ScratchpadEventType,
    ThesisDataContract,
)
from app.services.harness.budget import apply_harness_budget_guardrails
from app.services.harness.scratchpad import append_scratchpad_event, create_scratchpad_run
from app.services.researcher.pre_review import build_event_episode


@dataclass(frozen=True)
class ThesisIntakeHarnessResult:
    event_episode: EventEpisode
    cycle: ResearchHarnessCycle
    findings: list[ResearchFinding]
    tasks: list[ResearchTask]
    scratchpad_run: ResearchScratchpadRun | None = None


def build_thesis_intake_harness_cycle(
    *,
    thesis: ResearchThesis,
    signal,
    pre_review,
    research_design: ResearchDesignDraft,
    data_contract: ThesisDataContract,
    existing_tasks: list[ResearchTask] | None = None,
    scratchpad_base_dir: Path | str | None = None,
) -> ThesisIntakeHarnessResult:
    """Create the first Harness task set after a conversation-first thesis intake."""

    event_episode = build_event_episode(thesis, signal, research_design).model_copy(
        update={
            "features": {
                **signal.features,
                "data_contract_status": data_contract.status.value,
                "data_contract_can_run": data_contract.can_run,
                "pre_review_completeness_score": pre_review.completeness_score,
                "pre_review_condition_clarity_score": pre_review.condition_clarity_score,
                "pre_review_commonness_risk_score": pre_review.commonness_risk_score,
            },
            "missing_evidence": list(
                dict.fromkeys(
                    [
                        *event_episode_missing_evidence(data_contract, research_design),
                        *research_design.missing_evidence,
                    ]
                )
            ),
        }
    )
    tasks = _initial_tasks_for_thesis(thesis, event_episode, pre_review, research_design, data_contract)
    tasks, _budget_decisions = apply_harness_budget_guardrails(tasks, existing_tasks=existing_tasks or [])
    finding = _finding_for_intake(thesis, event_episode, pre_review, research_design, data_contract, tasks)
    cycle = ResearchHarnessCycle(
        cycle_id=f"harness_cycle_intake_{thesis.thesis_id}_{uuid4().hex[:8]}",
        thesis_id=thesis.thesis_id,
        signal_id=event_episode.signal_id,
        source="assistant_thesis_intake",
        finding_ids=[finding.finding_id],
        task_ids=[task.task_id for task in tasks],
        summary=(
            f"Assistant intake generated {len(tasks)} first research task(s) for "
            f"{research_design.inferred_strategy_family.value}; "
            f"pre_review={pre_review.status.value}, data_contract={data_contract.status.value}."
        ),
    )
    scratchpad_run = None
    if scratchpad_base_dir is not False:
        scratchpad_run = _write_scratchpad(
            thesis=thesis,
            event_episode=event_episode,
            pre_review=pre_review,
            research_design=research_design,
            data_contract=data_contract,
            finding=finding,
            tasks=tasks,
            base_dir=scratchpad_base_dir,
        )
    return ThesisIntakeHarnessResult(
        event_episode=event_episode,
        cycle=cycle,
        findings=[finding],
        tasks=tasks,
        scratchpad_run=scratchpad_run,
    )


def event_episode_missing_evidence(
    data_contract: ThesisDataContract,
    research_design: ResearchDesignDraft,
) -> list[str]:
    gaps = []
    if data_contract.mismatches:
        gaps.extend(data_contract.mismatches)
    if data_contract.warnings:
        gaps.extend(data_contract.warnings)
    if not data_contract.can_run:
        gaps.append("data_contract_cannot_run")
    gaps.extend(research_design.missing_evidence)
    return list(dict.fromkeys(gaps))


def _initial_tasks_for_thesis(
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    pre_review,
    research_design: ResearchDesignDraft,
    data_contract: ThesisDataContract,
) -> list[ResearchTask]:
    tasks: list[ResearchTask] = []
    if pre_review.status == PreReviewStatus.NEEDS_CLARIFICATION:
        tasks.append(
            _task(
                task_type=ResearchTaskType.STRATEGY_FAMILY_PRIORITY_REVIEW,
                thesis=thesis,
                event_episode=event_episode,
                subject_type="thesis",
                subject_id=thesis.thesis_id,
                hypothesis="The thesis should not generate code until its missing structure and ambiguous conditions are narrowed.",
                rationale="Pre-review classified the thesis as needs_clarification.",
                required_experiments=[
                    "answer the blocking pre-review questions",
                    "rewrite vague conditions into thresholds, windows, or named states",
                    "confirm whether this is event-driven or continuous-alpha evaluation",
                ],
                success_metrics=["pre_review status improves to can_proceed_with_assumptions or ready_for_design"],
                failure_conditions=["core entry/exit/invalidation remains undefined"],
                priority_score=90,
                estimated_cost=5,
            )
        )
    if data_contract.mismatches or data_contract.warnings or research_design.missing_evidence:
        tasks.append(
            _task(
                task_type=ResearchTaskType.DATA_SUFFICIENCY_REVIEW,
                thesis=thesis,
                event_episode=event_episode,
                subject_type="thesis",
                subject_id=thesis.thesis_id,
                hypothesis="The first test must explicitly state which evidence is real, proxied, or unavailable.",
                rationale="The thesis/data contract found missing or adjusted data requirements.",
                required_experiments=[
                    *event_episode_missing_evidence(data_contract, research_design),
                    "decide whether an OHLCV proxy is acceptable for the first pass",
                ],
                success_metrics=["data contract can run", "missing evidence is either resolved or recorded as a limitation"],
                failure_conditions=["strategy conclusion depends on unavailable evidence"],
                priority_score=86,
                estimated_cost=15,
            )
        )
    tasks.append(
        _task(
            task_type=ResearchTaskType.BASELINE_TEST,
            thesis=thesis,
            event_episode=event_episode,
            subject_type="thesis",
            subject_id=thesis.thesis_id,
            hypothesis="The thesis should be judged against matched baselines before any variant optimization.",
            rationale="New thesis intake requires a baseline board before deeper strategy generation.",
            required_experiments=[
                f"run baseline set: {', '.join(research_design.baseline_set)}",
                "record test period, symbols, timeframe, fees, and slippage assumptions",
            ],
            success_metrics=["baseline report exists", "best baseline is identified", "strategy family comparison is reproducible"],
            failure_conditions=["no matched baseline can be constructed"],
            priority_score=78,
            estimated_cost=25,
        )
    )
    if research_design.evaluation_type == EvaluationType.EVENT_DRIVEN_ALPHA:
        tasks.append(
            _task(
                task_type=ResearchTaskType.EVENT_FREQUENCY_SCAN,
                thesis=thesis,
                event_episode=event_episode,
                subject_type="strategy_family",
                subject_id=research_design.inferred_strategy_family.value,
                hypothesis="Before strategy coding, the system should know whether this event family appears often enough to study.",
                rationale="Event-driven theses can stall if the event definition is too rare or data coverage is too narrow.",
                required_experiments=[
                    "scan declared timeframe and available symbols for setup_count and trigger_count",
                    "compare strict and relaxed event definitions without selecting PnL winners",
                ],
                success_metrics=["event_count and trigger_count are reported", "sample sufficiency is judged before coding"],
                failure_conditions=["event frequency is too low for the planned validation profile"],
                priority_score=84,
                estimated_cost=30,
            )
        )
    else:
        tasks.append(
            _task(
                task_type=ResearchTaskType.REGIME_BUCKET_TEST,
                thesis=thesis,
                event_episode=event_episode,
                subject_type="strategy_family",
                subject_id=research_design.inferred_strategy_family.value,
                hypothesis="Continuous-alpha theses should be checked against baseline-implied regime buckets early.",
                rationale="The system should avoid optimizing a continuous signal against a single smooth market segment.",
                required_experiments=["bucket baseline results by trend, range, volatility, and drawdown state"],
                success_metrics=["regime bucket performance is reported", "no single regime silently dominates the conclusion"],
                failure_conditions=["performance only appears in one unplanned regime bucket"],
                priority_score=72,
                estimated_cost=25,
            )
        )
    return tasks


def _finding_for_intake(
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    pre_review,
    research_design: ResearchDesignDraft,
    data_contract: ThesisDataContract,
    tasks: list[ResearchTask],
) -> ResearchFinding:
    severity = (
        ResearchFindingSeverity.HIGH
        if pre_review.status == PreReviewStatus.NEEDS_CLARIFICATION or not data_contract.can_run
        else ResearchFindingSeverity.MEDIUM
        if data_contract.warnings or research_design.missing_evidence
        else ResearchFindingSeverity.LOW
    )
    observations = [
        f"pre_review_status={pre_review.status.value}",
        f"completeness_score={pre_review.completeness_score}",
        f"condition_clarity_score={pre_review.condition_clarity_score}",
        f"commonness_risk_score={pre_review.commonness_risk_score}",
        f"strategy_family={research_design.inferred_strategy_family.value}",
        f"evaluation_type={research_design.evaluation_type.value}",
        f"validation_data_sufficiency_level={research_design.validation_data_sufficiency_level.value}",
        f"data_contract_status={data_contract.status.value}",
        f"signal_timeframe={event_episode.timeframe}",
    ]
    return ResearchFinding(
        finding_id=f"finding_intake_{thesis.thesis_id}_{uuid4().hex[:8]}",
        thesis_id=thesis.thesis_id,
        signal_id=event_episode.signal_id,
        finding_type="thesis_intake_review",
        severity=severity,
        summary="Conversation-first thesis intake created a research design and first Harness task queue.",
        observations=observations,
        evidence_gaps=event_episode_missing_evidence(data_contract, research_design),
        next_task_ids=[task.task_id for task in tasks],
        evidence_refs=[
            f"thesis:{thesis.thesis_id}",
            f"event_episode:{event_episode.event_id}",
            f"thesis_data_contract:{data_contract.contract_id}",
            f"research_design:{research_design.design_id}",
        ],
    )


def _task(
    *,
    task_type: ResearchTaskType,
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    subject_type: str,
    subject_id: str,
    hypothesis: str,
    rationale: str,
    required_experiments: list[str],
    success_metrics: list[str],
    failure_conditions: list[str],
    priority_score: float,
    estimated_cost: int,
) -> ResearchTask:
    return ResearchTask(
        task_id=f"task_{task_type.value}_{subject_id}_{uuid4().hex[:8]}",
        task_type=task_type,
        subject_type=subject_type,
        subject_id=subject_id,
        thesis_id=thesis.thesis_id,
        signal_id=event_episode.signal_id,
        hypothesis=hypothesis,
        rationale=rationale,
        required_experiments=list(dict.fromkeys(required_experiments)),
        success_metrics=success_metrics,
        failure_conditions=failure_conditions,
        required_data_level=event_episode.validation_data_sufficiency_level,
        estimated_cost=estimated_cost,
        priority_score=priority_score,
        status=ResearchTaskStatus.PROPOSED,
        autonomy_level=1,
        evidence_refs=[f"thesis:{thesis.thesis_id}", f"event_episode:{event_episode.event_id}"],
    )


def _write_scratchpad(
    *,
    thesis: ResearchThesis,
    event_episode: EventEpisode,
    pre_review,
    research_design: ResearchDesignDraft,
    data_contract: ThesisDataContract,
    finding: ResearchFinding,
    tasks: list[ResearchTask],
    base_dir: Path | str | None,
) -> ResearchScratchpadRun:
    run_id = f"intake_{thesis.thesis_id}_{uuid4().hex[:8]}"
    run = create_scratchpad_run(
        run_id=run_id,
        purpose="conversation_first_thesis_intake",
        base_dir=base_dir or Path(".qo") / "scratchpad",
    )
    event_count = 0
    append_scratchpad_event(
        run_id=run_id,
        event_type=ScratchpadEventType.NOTE,
        thesis_id=thesis.thesis_id,
        payload={
            "thesis": thesis.model_dump(mode="json"),
            "pre_review": pre_review.model_dump(mode="json"),
            "research_design": research_design.model_dump(mode="json"),
            "data_contract": data_contract.model_dump(mode="json"),
            "event_episode": event_episode.model_dump(mode="json"),
        },
        base_dir=base_dir or Path(".qo") / "scratchpad",
        evidence_refs=[f"thesis:{thesis.thesis_id}"],
    )
    event_count += 1
    append_scratchpad_event(
        run_id=run_id,
        event_type=ScratchpadEventType.RESEARCH_FINDING,
        thesis_id=thesis.thesis_id,
        payload=finding.model_dump(mode="json"),
        base_dir=base_dir or Path(".qo") / "scratchpad",
        evidence_refs=finding.evidence_refs,
    )
    event_count += 1
    for task in tasks:
        append_scratchpad_event(
            run_id=run_id,
            event_type=ScratchpadEventType.RESEARCH_TASK,
            thesis_id=thesis.thesis_id,
            task_id=task.task_id,
            payload=task.model_dump(mode="json"),
            base_dir=base_dir or Path(".qo") / "scratchpad",
            evidence_refs=task.evidence_refs,
        )
        event_count += 1
    return run.model_copy(update={"event_count": event_count})
