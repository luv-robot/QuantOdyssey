from __future__ import annotations

import hashlib
from datetime import datetime

from app.models import (
    BaselineImpliedRegimeReport,
    DataSufficiencyLevel,
    ResearchFinding,
    ResearchTask,
    ResearchTaskType,
    ResearchThesis,
    ReviewSession,
    StrategyFamily,
    StrategyFamilyBaselineBoard,
    ThesisInboxItem,
    ThesisInboxSource,
    ThesisInboxStatus,
    ThesisStatus,
)


def build_thesis_inbox_items(
    *,
    research_tasks: list[ResearchTask] | None = None,
    findings: list[ResearchFinding] | None = None,
    review_sessions: list[ReviewSession] | None = None,
    baseline_board: StrategyFamilyBaselineBoard | None = None,
    regime_report: BaselineImpliedRegimeReport | None = None,
    limit: int = 12,
) -> list[ThesisInboxItem]:
    """Convert Harness evidence into user-reviewable research ideas.

    These items are suggestions, not accepted theses. The point is to keep
    research moving while preserving the human gate at thesis acceptance.
    """

    items: list[ThesisInboxItem] = []
    for session in review_sessions or []:
        if session.next_experiments:
            items.append(_item_from_review_session(session))

    for finding in findings or []:
        if finding.evidence_gaps:
            items.append(_item_from_data_gap(finding))
        elif finding.severity.value in {"high", "medium"}:
            items.append(_item_from_failure_finding(finding))

    for task in research_tasks or []:
        if task.task_type == ResearchTaskType.WATCHLIST_REVIEW:
            items.append(_item_from_watchlist_task(task))

    if baseline_board is not None and baseline_board.best_family:
        items.append(_item_from_baseline_board(baseline_board))

    if regime_report is not None:
        items.append(_item_from_regime_report(regime_report))

    deduped: dict[str, ThesisInboxItem] = {}
    for item in sorted(items, key=lambda value: value.priority_score, reverse=True):
        deduped.setdefault(item.fingerprint, item)
    return list(deduped.values())[:limit]


def convert_inbox_item_to_thesis(
    item: ThesisInboxItem,
    *,
    author: str = "harness_assisted",
    thesis_id: str | None = None,
) -> ResearchThesis:
    return ResearchThesis(
        thesis_id=thesis_id or f"thesis_from_{item.item_id}",
        title=item.title,
        author=author,
        status=ThesisStatus.DRAFT,
        market_observation=item.proposed_observation,
        hypothesis=item.proposed_hypothesis,
        trade_logic=item.proposed_trade_logic,
        expected_regimes=[_strategy_family_label(item.strategy_family)],
        invalidation_conditions=item.suggested_failure_conditions or ["The suggested edge fails matched baseline tests."],
        risk_notes=[
            "Generated from Thesis Inbox; requires human review before implementation.",
            f"source={item.source.value}",
        ],
        constraints=[
            "do not enter paper trading without explicit human approval",
            f"source_inbox_item={item.item_id}",
        ],
    )


def mark_inbox_item_converted(item: ThesisInboxItem, thesis_id: str) -> ThesisInboxItem:
    return item.model_copy(
        update={
            "status": ThesisInboxStatus.CONVERTED_TO_THESIS,
            "linked_thesis_id": thesis_id,
            "updated_at": datetime.utcnow(),
        }
    )


def build_thesis_inbox_digest(items: list[ThesisInboxItem], *, max_items: int = 8) -> str:
    if not items:
        return "Harness did not generate new thesis inbox suggestions in this cycle."
    lines = ["Harness Thesis Inbox Digest", ""]
    for index, item in enumerate(items[:max_items], start=1):
        lines.extend(
            [
                f"{index}. {item.title}",
                f"   source: {item.source.value} | priority: {item.priority_score:.0f}",
                f"   why: {item.rationale}",
                f"   next: {', '.join(item.suggested_experiments[:3]) or 'review the idea'}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _item_from_review_session(session: ReviewSession) -> ThesisInboxItem:
    experiment = session.next_experiments[0]
    source_key = f"review:{session.session_id}:{experiment}"
    scorecard = session.scorecard
    strategy_family = _strategy_family_from_scorecard(scorecard)
    return _item(
        source=ThesisInboxSource.REVIEW_SESSION_DERIVED,
        source_key=source_key,
        title=f"Follow up ReviewSession: {session.strategy_id}",
        summary=f"ReviewSession proposed {len(session.next_experiments)} next experiment(s).",
        rationale="A recent AI review produced concrete next experiments that can become user-approved thesis drafts.",
        proposed_observation="Recent strategy review exposed unresolved evidence and follow-up experiments.",
        proposed_hypothesis=experiment,
        proposed_trade_logic="Treat this as a research question first; design a minimal experiment before generating new strategy code.",
        suggested_questions=[question.question for question in session.ai_questions[:3]],
        suggested_experiments=session.next_experiments,
        suggested_success_metrics=["follow-up experiment produces comparable baseline evidence"],
        suggested_failure_conditions=["follow-up result remains below matched baseline", "sample count remains insufficient"],
        strategy_family=strategy_family,
        required_data_level=_data_level_from_scorecard(scorecard),
        priority_score=76,
        linked_thesis_id=session.thesis_id,
        linked_strategy_id=session.strategy_id,
        evidence_refs=[f"review_session:{session.session_id}"],
    )


def _item_from_data_gap(finding: ResearchFinding) -> ThesisInboxItem:
    gap = finding.evidence_gaps[0]
    return _item(
        source=ThesisInboxSource.DATA_GAP_DERIVED,
        source_key=f"data_gap:{finding.finding_id}:{gap}",
        title=f"Resolve data gap: {gap[:72]}",
        summary="Harness found a data gap that may block reliable strategy judgment.",
        rationale=finding.summary,
        proposed_observation=f"Current evidence is missing or weak: {gap}",
        proposed_hypothesis="Resolving the data gap should improve whether the strategy family can be evaluated fairly.",
        proposed_trade_logic="Do not alter strategy logic yet; first test whether the missing evidence changes the review conclusion.",
        suggested_questions=["Is this data gap essential for the thesis, or only a nice-to-have confirmation?"],
        suggested_experiments=[*finding.evidence_gaps[:4], "rerun the ReviewSession after the evidence gap is addressed"],
        suggested_success_metrics=["data gap is resolved or explicitly accepted", "AI review no longer treats data absence as a blocker"],
        suggested_failure_conditions=["strategy conclusion still depends on unavailable evidence"],
        strategy_family=StrategyFamily.GENERAL_OR_UNKNOWN,
        required_data_level=DataSufficiencyLevel.L1_FUNDING_OI,
        priority_score=84,
        linked_thesis_id=finding.thesis_id,
        linked_strategy_id=finding.strategy_id,
        evidence_refs=[f"research_finding:{finding.finding_id}", *finding.evidence_refs],
    )


def _item_from_failure_finding(finding: ResearchFinding) -> ThesisInboxItem:
    return _item(
        source=ThesisInboxSource.FAILURE_DERIVED,
        source_key=f"failure:{finding.finding_id}",
        title=f"Turn failure into a thesis: {finding.finding_type}",
        summary="A failure finding can become a bounded next research question instead of a dead end.",
        rationale=finding.summary,
        proposed_observation="A recent experiment failed or remained fragile under the current evidence standard.",
        proposed_hypothesis="The failure may be conditional on regime, sample coverage, or baseline mismatch rather than universally invalid.",
        proposed_trade_logic="Generate a diagnostic experiment before testing new variants.",
        suggested_questions=["Which condition would make this failure informative rather than final?"],
        suggested_experiments=finding.observations[:4] or ["cluster this failure against prior review cases"],
        suggested_success_metrics=["failure pattern is reusable", "next task avoids repeating the same weak test"],
        suggested_failure_conditions=["no distinguishable failure pattern is found"],
        priority_score=70,
        linked_thesis_id=finding.thesis_id,
        linked_strategy_id=finding.strategy_id,
        evidence_refs=[f"research_finding:{finding.finding_id}", *finding.evidence_refs],
    )


def _item_from_watchlist_task(task: ResearchTask) -> ThesisInboxItem:
    return _item(
        source=ThesisInboxSource.WATCHLIST_DERIVED,
        source_key=f"watchlist:{task.task_id}",
        title=f"Watchlist review: {task.subject_id}",
        summary="Harness found a candidate that may deserve watchlist review.",
        rationale=task.rationale,
        proposed_observation="A strategy variant has enough supportive evidence to ask whether it deserves deeper tracking.",
        proposed_hypothesis=task.hypothesis,
        proposed_trade_logic="Review prerequisites and unresolved questions before any paper-trading promotion.",
        suggested_experiments=task.required_experiments,
        suggested_success_metrics=task.success_metrics,
        suggested_failure_conditions=task.failure_conditions,
        required_data_level=task.required_data_level,
        priority_score=task.priority_score,
        linked_thesis_id=task.thesis_id,
        linked_strategy_id=task.strategy_id,
        linked_task_ids=[task.task_id],
        evidence_refs=[f"research_task:{task.task_id}", *task.evidence_refs],
    )


def _item_from_baseline_board(board: StrategyFamilyBaselineBoard) -> ThesisInboxItem:
    best = next((row for row in board.rows if row.strategy_family == board.best_family), None)
    best_metrics = "" if best is None else f" return={best.total_return:.4f}, pf={best.profit_factor:.2f}"
    return _item(
        source=ThesisInboxSource.BASELINE_DERIVED,
        source_key=f"baseline:{board.board_id}:{board.best_family}",
        title=f"Explore baseline leader: {board.best_family}",
        summary=f"Generic baseline board currently favors {board.best_family}.{best_metrics}",
        rationale="Baseline performance differences can reveal where the current data window rewards simple, transparent strategy families.",
        proposed_observation=f"{board.best_family} is the current best generic baseline across the tested universe.",
        proposed_hypothesis="A human-reviewed thesis in the leading baseline family may provide a more useful research direction than forcing low-frequency event templates.",
        proposed_trade_logic="Start from a plain-English thesis and compare it against the exact baseline family that motivated it.",
        suggested_questions=["Is this baseline strength a regime artifact or a repeatable family-level edge?"],
        suggested_experiments=["build a human-reviewed thesis draft for the leading baseline family", "run cross-symbol validation", "bucket by regime"],
        suggested_success_metrics=["new thesis beats the generic baseline under matched costs", "effect survives at least one OOS split"],
        suggested_failure_conditions=["custom thesis fails to beat the simple baseline", "result is concentrated in one symbol"],
        priority_score=72,
        evidence_refs=[f"strategy_family_baseline_board:{board.board_id}"],
    )


def _item_from_regime_report(report: BaselineImpliedRegimeReport) -> ThesisInboxItem:
    leader = report.leading_baselines[0] if report.leading_baselines else report.regime_label
    return _item(
        source=ThesisInboxSource.REGIME_DERIVED,
        source_key=f"regime:{report.report_id}:{report.regime_label}",
        title=f"Regime question: {report.regime_label}",
        summary=f"Baseline-implied regime is {report.regime_label} with confidence {report.confidence:.2f}.",
        rationale="Regime changes should steer what kind of thesis the user is asked to review next.",
        proposed_observation=f"Current baseline components point toward {report.regime_label}; leading baseline: {leader}.",
        proposed_hypothesis="A strategy family aligned with the current regime should be tested before spending more budget on mismatched families.",
        proposed_trade_logic="Generate a regime-aligned thesis draft and require baseline/regime bucket comparison.",
        suggested_questions=["Which strategy family should be favored if this regime label is only provisional?"],
        suggested_experiments=["run regime bucket validation", "compare leading and lagging baseline families", "create one human-reviewed regime-aligned thesis"],
        suggested_success_metrics=["regime-aligned thesis improves over mismatched baseline families"],
        suggested_failure_conditions=["baseline-implied regime flips quickly", "leading family loses after OOS split"],
        priority_score=68 + min(20, report.confidence * 20),
        evidence_refs=[f"baseline_implied_regime:{report.report_id}"],
    )


def _item(
    *,
    source: ThesisInboxSource,
    source_key: str,
    title: str,
    summary: str,
    rationale: str,
    proposed_observation: str,
    proposed_hypothesis: str,
    proposed_trade_logic: str,
    suggested_questions: list[str] | None = None,
    suggested_experiments: list[str] | None = None,
    suggested_success_metrics: list[str] | None = None,
    suggested_failure_conditions: list[str] | None = None,
    strategy_family: StrategyFamily = StrategyFamily.GENERAL_OR_UNKNOWN,
    required_data_level: DataSufficiencyLevel = DataSufficiencyLevel.L0_OHLCV_ONLY,
    priority_score: float = 50,
    linked_thesis_id: str | None = None,
    linked_strategy_id: str | None = None,
    linked_task_ids: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> ThesisInboxItem:
    fingerprint = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:16]
    return ThesisInboxItem(
        item_id=f"inbox_{source.value}_{fingerprint}",
        fingerprint=fingerprint,
        source=source,
        title=title,
        summary=summary,
        rationale=rationale,
        proposed_observation=proposed_observation,
        proposed_hypothesis=proposed_hypothesis,
        proposed_trade_logic=proposed_trade_logic,
        suggested_questions=suggested_questions or [],
        suggested_experiments=suggested_experiments or [],
        suggested_success_metrics=suggested_success_metrics or [],
        suggested_failure_conditions=suggested_failure_conditions or [],
        strategy_family=strategy_family,
        required_data_level=required_data_level,
        priority_score=max(0, min(100, priority_score)),
        linked_thesis_id=linked_thesis_id,
        linked_strategy_id=linked_strategy_id,
        linked_task_ids=linked_task_ids or [],
        evidence_refs=list(dict.fromkeys(evidence_refs or [])),
    )


def _strategy_family_from_scorecard(scorecard: dict[str, float | int | str | bool | None]) -> StrategyFamily:
    value = scorecard.get("strategy_family")
    if isinstance(value, str):
        try:
            return StrategyFamily(value)
        except ValueError:
            return StrategyFamily.GENERAL_OR_UNKNOWN
    return StrategyFamily.GENERAL_OR_UNKNOWN


def _data_level_from_scorecard(scorecard: dict[str, float | int | str | bool | None]) -> DataSufficiencyLevel:
    value = scorecard.get("validation_data_sufficiency_level")
    if isinstance(value, str):
        try:
            return DataSufficiencyLevel(value)
        except ValueError:
            return DataSufficiencyLevel.L0_OHLCV_ONLY
    return DataSufficiencyLevel.L0_OHLCV_ONLY


def _strategy_family_label(strategy_family: StrategyFamily) -> str:
    return strategy_family.value.replace("_", " ")
