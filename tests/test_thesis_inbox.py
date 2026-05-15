from app.models import (
    BaselineImpliedRegimeReport,
    DataSufficiencyLevel,
    ResearchFinding,
    ResearchFindingSeverity,
    ResearchMaturityScore,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    ReviewSession,
    StrategyFamilyBaselineBoard,
    StrategyFamilyBaselineRow,
    ThesisInboxSource,
    ThesisInboxStatus,
    ThesisStatus,
)
from app.services.harness import (
    build_thesis_inbox_digest,
    build_thesis_inbox_items,
    convert_inbox_item_to_thesis,
    mark_inbox_item_converted,
)
from app.storage import QuantRepository


def test_harness_builds_thesis_inbox_items_from_multiple_sources() -> None:
    items = build_thesis_inbox_items(
        research_tasks=[_watchlist_task()],
        findings=[_data_gap_finding()],
        review_sessions=[_review_session()],
        baseline_board=_baseline_board(),
        regime_report=_regime_report(),
    )

    sources = {item.source for item in items}
    assert ThesisInboxSource.REVIEW_SESSION_DERIVED in sources
    assert ThesisInboxSource.DATA_GAP_DERIVED in sources
    assert ThesisInboxSource.WATCHLIST_DERIVED in sources
    assert ThesisInboxSource.BASELINE_DERIVED in sources
    assert ThesisInboxSource.REGIME_DERIVED in sources
    assert all(item.status == ThesisInboxStatus.SUGGESTED for item in items)
    assert all(item.approval_required for item in items)


def test_thesis_inbox_items_convert_to_draft_thesis_and_persist() -> None:
    repository = QuantRepository()
    item = build_thesis_inbox_items(review_sessions=[_review_session()], limit=1)[0]
    thesis = convert_inbox_item_to_thesis(item, thesis_id="thesis_from_inbox_test")
    converted = mark_inbox_item_converted(item, thesis.thesis_id)

    repository.save_thesis_inbox_item(converted)
    repository.save_research_thesis(thesis)

    assert thesis.status == ThesisStatus.DRAFT
    assert repository.get_thesis_inbox_item(item.item_id).linked_thesis_id == thesis.thesis_id
    assert repository.query_thesis_inbox_items(status=ThesisInboxStatus.CONVERTED_TO_THESIS.value) == [converted]
    assert repository.get_research_thesis(thesis.thesis_id) == thesis


def test_thesis_inbox_digest_is_human_readable() -> None:
    items = build_thesis_inbox_items(review_sessions=[_review_session()], limit=1)
    digest = build_thesis_inbox_digest(items)

    assert "Harness Thesis Inbox Digest" in digest
    assert "review_session_derived" in digest


def _review_session() -> ReviewSession:
    return ReviewSession(
        session_id="review_session_inbox",
        thesis_id="thesis_inbox",
        signal_id="signal_inbox",
        strategy_id="strategy_inbox",
        scorecard={
            "validation_data_sufficiency_level": DataSufficiencyLevel.L1_FUNDING_OI.value,
            "strategy_family": "funding_crowding_fade",
        },
        next_experiments=[
            "Test whether funding crowding still matters after regime and baseline controls.",
            "Compare strategy returns with funding-only baseline over identical windows.",
        ],
        maturity_score=ResearchMaturityScore(
            overall_score=44,
            thesis_clarity=70,
            data_sufficiency=45,
            sample_maturity=30,
            baseline_advantage=20,
            robustness=35,
            regime_stability=40,
            failure_understanding=55,
            implementation_safety=80,
            overfit_risk=65,
            stage="needs_more_evidence",
            blockers=["baseline advantage is weak"],
        ),
    )


def _data_gap_finding() -> ResearchFinding:
    return ResearchFinding(
        finding_id="finding_data_gap",
        thesis_id="thesis_inbox",
        signal_id="signal_inbox",
        strategy_id="strategy_inbox",
        finding_type="data_gap",
        severity=ResearchFindingSeverity.HIGH,
        summary="Orderflow evidence is missing for breakout acceptance.",
        evidence_gaps=["orderflow acceptance after breakout is missing"],
    )


def _watchlist_task() -> ResearchTask:
    return ResearchTask(
        task_id="task_watchlist",
        task_type=ResearchTaskType.WATCHLIST_REVIEW,
        subject_type="strategy",
        subject_id="strategy_watchlist",
        thesis_id="thesis_inbox",
        signal_id="signal_inbox",
        strategy_id="strategy_watchlist",
        hypothesis="Candidate may deserve watchlist review before paper trading.",
        rationale="Strategy beat matched baseline in the latest review.",
        required_experiments=["confirm remaining review blockers"],
        success_metrics=["watchlist rationale is explicit"],
        failure_conditions=["unresolved review blockers remain"],
        required_data_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
        priority_score=72,
        status=ResearchTaskStatus.PROPOSED,
    )


def _baseline_board() -> StrategyFamilyBaselineBoard:
    return StrategyFamilyBaselineBoard(
        board_id="baseline_board_inbox",
        rows=[
            StrategyFamilyBaselineRow(
                strategy_family="time_series_trend",
                description="trend baseline",
                total_return=0.18,
                profit_factor=1.5,
                sharpe=0.8,
                max_drawdown=-0.08,
                trades=120,
            )
        ],
        best_family="time_series_trend",
    )


def _regime_report() -> BaselineImpliedRegimeReport:
    return BaselineImpliedRegimeReport(
        report_id="regime_inbox",
        source_baseline_board_id="baseline_board_inbox",
        regime_label="directional_trend",
        confidence=0.72,
        component_scores={"trend": 78},
        leading_baselines=["time_series_trend"],
        lagging_baselines=["grid_range"],
    )
