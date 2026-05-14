from datetime import datetime

from app.models import (
    BacktestReport,
    BacktestStatus,
    BaselineComparisonReport,
    BaselineResult,
    DataSufficiencyLevel,
    EvaluationType,
    EventEpisode,
    EventEpisodeStage,
    PreReviewStatus,
    ResearchDesignDraft,
    ReviewCase,
    ReviewResult,
    RobustnessReport,
    StrategyFamily,
    ThesisPreReview,
)
from app.services.reviewer import build_review_session
from app.storage import QuantRepository


def sample_pre_review() -> ThesisPreReview:
    return ThesisPreReview(
        pre_review_id="pre_review_session",
        thesis_id="thesis_review_session",
        status=PreReviewStatus.CAN_PROCEED_WITH_ASSUMPTIONS,
        completeness_score=90,
        condition_clarity_score=80,
        commonness_risk_score=45,
        unresolved_questions=["Which missing evidence should be added first?"],
    )


def sample_design() -> ResearchDesignDraft:
    return ResearchDesignDraft(
        design_id="design_review_session",
        thesis_id="thesis_review_session",
        pre_review_id="pre_review_session",
        thesis_summary="Funding crowding fade short.",
        inferred_strategy_family=StrategyFamily.FUNDING_CROWDING_FADE,
        evaluation_type=EvaluationType.EVENT_DRIVEN_ALPHA,
        data_sufficiency_level=DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION,
        validation_data_sufficiency_level=DataSufficiencyLevel.L1_FUNDING_OI,
        missing_evidence=["orderbook", "liquidation", "cvd"],
        event_definition_draft="Funding/OI extreme plus failed breakout.",
        baseline_set=["funding_extreme_only_proxy", "funding_plus_oi_proxy"],
        required_data=["ohlcv", "funding_rate", "open_interest"],
        what_this_tests=["L1 proxy evidence."],
        what_this_does_not_test=["Orderbook absorption."],
        proceed_recommendation=PreReviewStatus.CAN_PROCEED_WITH_ASSUMPTIONS,
    )


def sample_event() -> EventEpisode:
    return EventEpisode(
        event_id="event_review_session",
        thesis_id="thesis_review_session",
        signal_id="signal_review_session",
        strategy_family=StrategyFamily.FUNDING_CROWDING_FADE,
        evaluation_type=EvaluationType.EVENT_DRIVEN_ALPHA,
        stage=EventEpisodeStage.SETUP,
        direction="short",
        symbol="BTC/USDT",
        timeframe="5m",
        trigger_window_bars=3,
        data_sufficiency_level=DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION,
        validation_data_sufficiency_level=DataSufficiencyLevel.L1_FUNDING_OI,
        trigger_definition="Failed breakout within 3 bars.",
        missing_evidence=["orderbook", "liquidation", "cvd"],
    )


def sample_backtest() -> BacktestReport:
    return BacktestReport(
        backtest_id="bt_review_session",
        strategy_id="strategy_review_session",
        timerange="20240101-20260501",
        trades=123,
        win_rate=0.58,
        profit_factor=1.62,
        sharpe=1.2,
        max_drawdown=-0.06,
        total_return=0.18,
        status=BacktestStatus.PASSED,
        created_at=datetime.utcnow(),
    )


def sample_baseline() -> BaselineComparisonReport:
    return BaselineComparisonReport(
        report_id="baseline_review_session",
        strategy_id="strategy_review_session",
        signal_id="signal_review_session",
        source_backtest_id="bt_review_session",
        strategy_total_return=0.18,
        strategy_profit_factor=1.62,
        best_baseline_name="funding_plus_oi_proxy",
        best_baseline_return=0.09,
        outperformed_best_baseline=True,
        baselines=[
            BaselineResult(
                name="funding_plus_oi_proxy",
                description="Funding plus OI baseline.",
                total_return=0.09,
                profit_factor=1.1,
                sharpe=0.4,
                max_drawdown=-0.08,
                trades=40,
            )
        ],
    )


def sample_robustness() -> RobustnessReport:
    return RobustnessReport(
        report_id="robustness_review_session",
        strategy_id="strategy_review_session",
        source_backtest_id="bt_review_session",
        baseline_report_id="baseline_review_session",
        monte_carlo_report_id="mc_review_session",
        validation_id="validation_review_session",
        statistical_confidence_score=72,
        robustness_score=84,
        passed=True,
        findings=["Strategy passed current robustness criteria."],
    )


def sample_review_case() -> ReviewCase:
    return ReviewCase(
        case_id="case_review_session",
        strategy_id="strategy_review_session",
        signal_id="signal_review_session",
        result=ReviewResult.PASSED,
        pattern="funding crowding fade",
        reusable_lessons=["Replace proxy baselines with event-level baselines."],
        avoid_conditions=["healthy trend acceptance"],
    )


def test_build_review_session_generates_evidence_and_maturity_score() -> None:
    session = build_review_session(
        sample_pre_review(),
        sample_design(),
        sample_event(),
        sample_backtest(),
        sample_baseline(),
        sample_robustness(),
        sample_review_case(),
    )

    assert session.session_id == "review_session_bt_review_session"
    assert session.maturity_score.overall_score > 0
    assert session.scorecard["profit_factor"] == 1.62
    assert session.evidence_for
    assert session.blind_spots
    assert session.ai_questions
    assert session.next_experiments
    assert any("orderbook" in blocker for blocker in session.maturity_score.blockers)


def test_review_session_uses_event_level_validation_scope() -> None:
    design = sample_design().model_copy(
        update={
            "data_sufficiency_level": DataSufficiencyLevel.L1_FUNDING_OI,
            "validation_data_sufficiency_level": DataSufficiencyLevel.L1_FUNDING_OI,
            "missing_evidence": [],
        }
    )
    event = sample_event().model_copy(
        update={
            "data_sufficiency_level": DataSufficiencyLevel.L1_FUNDING_OI,
            "validation_data_sufficiency_level": DataSufficiencyLevel.L0_OHLCV_ONLY,
            "missing_evidence": ["historical_open_interest"],
        }
    )

    session = build_review_session(
        sample_pre_review(),
        design,
        event,
        sample_backtest(),
        sample_baseline(),
        sample_robustness(),
        sample_review_case(),
    )

    assert session.scorecard["validation_data_sufficiency_level"] == DataSufficiencyLevel.L0_OHLCV_ONLY.value
    assert session.maturity_score.data_sufficiency == 55
    assert any("historical_open_interest" in blocker for blocker in session.maturity_score.blockers)
    assert any(claim.claim_id == "blind_spot_missing_evidence" for claim in session.blind_spots)


def test_repository_persists_review_sessions() -> None:
    repository = QuantRepository()
    session = build_review_session(
        sample_pre_review(),
        sample_design(),
        sample_event(),
        sample_backtest(),
        sample_baseline(),
        sample_robustness(),
        sample_review_case(),
    )

    repository.save_review_session(session)

    assert repository.get_review_session(session.session_id) == session
    assert repository.query_review_sessions(thesis_id=session.thesis_id) == [session]
    assert repository.query_review_sessions(strategy_id=session.strategy_id) == [session]
