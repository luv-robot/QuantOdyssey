from datetime import datetime

from app.models import (
    BacktestReport,
    BacktestStatus,
    BaselineComparisonReport,
    BaselineResult,
    PublicArtifactStatus,
    PublicArtifactVisibility,
    ResearchDesignDraft,
    ResearchMaturityScore,
    ResearchThesis,
    ReviewSession,
    StrategyFamily,
    StrategyManifest,
)
from app.services.publication import build_public_strategy_card, build_public_thesis_card
from app.storage import QuantRepository


def test_public_thesis_card_is_redacted_and_persisted() -> None:
    repository = QuantRepository()
    thesis = _thesis()
    card = build_public_thesis_card(
        thesis,
        design=_design(),
        review_session=_review_session(),
        baseline=_baseline(),
        visibility=PublicArtifactVisibility.PUBLIC,
        status=PublicArtifactStatus.PUBLISHED,
    )

    repository.save_public_thesis_card(card)

    assert card.public_id == f"public_thesis_{thesis.thesis_id}"
    assert "full_trade_logic" in card.redacted_fields
    assert "private" not in card.public_summary.lower()
    assert repository.get_public_thesis_card(card.public_id) == card
    assert repository.query_public_thesis_cards(visibility=PublicArtifactVisibility.PUBLIC.value) == [card]


def test_public_strategy_card_hides_code_path_but_keeps_metrics() -> None:
    repository = QuantRepository()
    strategy = _strategy()
    card = build_public_strategy_card(
        strategy,
        backtest=_backtest(),
        baseline=_baseline(),
        review_session=_review_session(),
        strategy_family=StrategyFamily.FUNDING_CROWDING_FADE,
        visibility=PublicArtifactVisibility.PUBLIC,
        status=PublicArtifactStatus.PUBLISHED,
    )

    repository.save_public_strategy_card(card)

    dumped = card.model_dump(mode="json")
    assert strategy.file_path not in str(dumped)
    assert "strategy_file_path" in card.redacted_fields
    assert card.public_metrics["profit_factor"] == 1.42
    assert repository.get_public_strategy_card(card.public_id) == card
    assert repository.query_public_strategy_cards(strategy_id=strategy.strategy_id) == [card]


def _thesis() -> ResearchThesis:
    return ResearchThesis(
        thesis_id="thesis_public",
        title="Funding Crowding Fade",
        market_observation="Funding and OI extremes can mark crowded positioning.",
        hypothesis="Crowded longs become vulnerable after failed continuation.",
        trade_logic="Short only after failure confirmation and defined stop.",
        expected_regimes=["event-driven crowding"],
        invalidation_conditions=["breakout acceptance remains strong"],
    )


def _design() -> ResearchDesignDraft:
    return ResearchDesignDraft(
        design_id="design_public",
        thesis_id="thesis_public",
        pre_review_id="pre_public",
        thesis_summary="Funding crowding thesis.",
        inferred_strategy_family=StrategyFamily.FUNDING_CROWDING_FADE,
        evaluation_type="event_driven_alpha",
        data_sufficiency_level="L1_ohlcv_funding_open_interest",
        event_definition_draft="funding + OI + failed breakout",
        baseline_set=["cash", "funding_only", "funding_plus_oi"],
        required_data=["OHLCV", "funding", "open_interest"],
        what_this_tests=["crowding reversal"],
        proceed_recommendation="ready_for_design",
    )


def _strategy() -> StrategyManifest:
    return StrategyManifest(
        strategy_id="strategy_public",
        signal_id="signal_public",
        thesis_id="thesis_public",
        name="FundingCrowdingFadePublic",
        file_path="/private/alpha/FundingCrowdingFadePublic.py",
        generated_at=datetime.utcnow(),
        timeframe="5m",
        symbols=["BTC/USDT:USDT"],
        assumptions=["funding is extreme", "OI is high", "breakout fails"],
        failure_modes=["strong trend accepts the breakout"],
    )


def _backtest() -> BacktestReport:
    return BacktestReport(
        backtest_id="bt_public",
        strategy_id="strategy_public",
        timerange="20240101-20260501",
        trades=92,
        win_rate=0.53,
        profit_factor=1.42,
        sharpe=0.9,
        max_drawdown=-0.07,
        total_return=0.14,
        status=BacktestStatus.PASSED,
    )


def _baseline() -> BaselineComparisonReport:
    return BaselineComparisonReport(
        report_id="baseline_public",
        strategy_id="strategy_public",
        signal_id="signal_public",
        source_backtest_id="bt_public",
        strategy_total_return=0.14,
        strategy_profit_factor=1.42,
        best_baseline_name="funding_plus_oi",
        best_baseline_return=0.08,
        outperformed_best_baseline=True,
        baselines=[
            BaselineResult(
                name="funding_plus_oi",
                description="simple public baseline",
                total_return=0.08,
                profit_factor=1.1,
                max_drawdown=-0.09,
                trades=100,
            )
        ],
    )


def _review_session() -> ReviewSession:
    return ReviewSession(
        session_id="review_public",
        thesis_id="thesis_public",
        signal_id="signal_public",
        strategy_id="strategy_public",
        next_experiments=["walk-forward validation", "orderflow acceptance check"],
        maturity_score=ResearchMaturityScore(
            overall_score=62,
            thesis_clarity=80,
            data_sufficiency=55,
            sample_maturity=58,
            baseline_advantage=65,
            robustness=60,
            regime_stability=50,
            failure_understanding=70,
            implementation_safety=90,
            overfit_risk=38,
            stage="research_watchlist",
        ),
    )
