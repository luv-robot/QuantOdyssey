from app.models import (
    DataSufficiencyLevel,
    EvaluationType,
    MarketSignal,
    PreReviewStatus,
    ResearchThesis,
    SignalType,
    StrategyFamily,
    ThesisStatus,
)
from app.services.researcher import (
    build_event_episode,
    build_research_design_draft,
    build_thesis_pre_review,
    generate_thesis_strategy_candidates,
)
from app.storage import QuantRepository
from datetime import datetime


def test_pre_review_asks_questions_for_vague_common_thesis() -> None:
    thesis = ResearchThesis(
        thesis_id="thesis_pre_review",
        title="RSI EMA breakout idea",
        status=ThesisStatus.DRAFT,
        market_observation="BTC often moves after obvious breakout.",
        hypothesis="Strong trend and volume may continue.",
        trade_logic="Use RSI and EMA to enter after breakout.",
        expected_regimes=["trend"],
        invalidation_conditions=["fails"],
    )

    pre_review = build_thesis_pre_review(thesis)

    assert pre_review.status == PreReviewStatus.NEEDS_CLARIFICATION
    assert pre_review.condition_clarity_score <= 70
    assert pre_review.commonness_risk_score >= 60
    assert 1 <= len(pre_review.questions) <= 8
    assert any("common" in item.lower() or "indicator" in item.lower() for item in pre_review.commonness_findings)
    assert pre_review.unresolved_questions


def test_research_design_infers_family_data_level_and_baselines() -> None:
    thesis = ResearchThesis(
        thesis_id="thesis_funding",
        title="Funding crowding fade",
        status=ThesisStatus.DRAFT,
        market_observation="Funding is extremely positive while BTC stops making new highs.",
        hypothesis="Crowded longs paying high funding may be forced to exit when price fails to extend.",
        trade_logic="Enter short after price closes back below the failed breakout level; exit on reclaim or stop above high.",
        expected_regimes=["normal liquidity", "not crash"],
        invalidation_conditions=["funding normalizes", "price accepts above breakout level"],
    )

    pre_review = build_thesis_pre_review(thesis)
    design = build_research_design_draft(thesis, pre_review)

    assert design.inferred_strategy_family == StrategyFamily.FUNDING_CROWDING_FADE
    assert design.evaluation_type == EvaluationType.EVENT_DRIVEN_ALPHA
    assert design.data_sufficiency_level == DataSufficiencyLevel.L1_FUNDING_OI
    assert "naive_event_entry" in design.baseline_set
    assert "funding_rate" in design.required_data


def test_research_design_separates_target_and_validation_data_level() -> None:
    thesis = ResearchThesis(
        thesis_id="thesis_funding_l1",
        title="Funding crowding fade with future orderbook evidence",
        status=ThesisStatus.DRAFT,
        market_observation="Funding and OI are high, while CVD and orderbook would help confirm crowded longs.",
        hypothesis="Crowded longs may exit after failed breakout and OI decline.",
        trade_logic="First test data level = L1 OHLCV + funding + OI; short after 3 bars fail above local high.",
        expected_regimes=["normal"],
        invalidation_conditions=["breakout acceptance remains true"],
    )

    pre_review = build_thesis_pre_review(thesis)
    design = build_research_design_draft(thesis, pre_review)

    assert design.data_sufficiency_level == DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION
    assert design.validation_data_sufficiency_level == DataSufficiencyLevel.L1_FUNDING_OI
    assert "orderbook" in design.missing_evidence
    assert "funding_rate" in design.required_data
    assert "orderbook" not in design.required_data


def test_event_episode_records_validation_scope() -> None:
    thesis = ResearchThesis(
        thesis_id="thesis_event_episode",
        title="Funding crowding fade short",
        status=ThesisStatus.DRAFT,
        market_observation="Positive funding and high OI show crowded longs.",
        hypothesis="Crowded longs may exit after failed breakout.",
        trade_logic="First test data level = L1 OHLCV + funding + OI. Test short side after 3 bars fail above local high.",
        expected_regimes=["normal"],
        invalidation_conditions=["breakout acceptance"],
    )
    signal = MarketSignal(
        signal_id="signal_event_episode",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="5m",
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=80,
        features={"funding_percentile_30d": 95, "open_interest_percentile_30d": 80},
        hypothesis="funding crowding",
        data_sources=["ohlcv", "funding", "oi"],
    )
    pre_review = build_thesis_pre_review(thesis)
    design = build_research_design_draft(thesis, pre_review)
    event = build_event_episode(thesis, signal, design)

    assert event.strategy_family == StrategyFamily.FUNDING_CROWDING_FADE
    assert event.direction == "short"
    assert event.trigger_window_bars == 3
    assert event.validation_data_sufficiency_level == DataSufficiencyLevel.L1_FUNDING_OI


def test_event_episode_marks_proxy_open_interest_as_missing_evidence() -> None:
    thesis = ResearchThesis(
        thesis_id="thesis_event_proxy_oi",
        title="Funding crowding fade short",
        status=ThesisStatus.DRAFT,
        market_observation="Positive funding and high OI show crowded longs.",
        hypothesis="Crowded longs may exit after failed breakout.",
        trade_logic="First test data level = L1 OHLCV + funding + OI. Test short side after 3 bars fail above local high.",
        expected_regimes=["normal"],
        invalidation_conditions=["breakout acceptance"],
    )
    signal = MarketSignal(
        signal_id="signal_event_proxy_oi",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=42,
        features={
            "funding_percentile_30d": 90,
            "open_interest_percentile_30d": 84,
            "open_interest_source": "volume_proxy",
        },
        hypothesis="funding crowding",
        data_sources=["ohlcv", "funding"],
    )
    pre_review = build_thesis_pre_review(thesis)
    design = build_research_design_draft(thesis, pre_review)
    event = build_event_episode(thesis, signal, design)

    assert "historical_open_interest" in event.missing_evidence
    assert event.validation_data_sufficiency_level == DataSufficiencyLevel.L0_OHLCV_ONLY


def test_repository_persists_pre_review_and_design() -> None:
    repository = QuantRepository()
    thesis = ResearchThesis(
        thesis_id="thesis_repo_pre_review",
        title="Failed breakout",
        status=ThesisStatus.DRAFT,
        market_observation="Price breaks a prior high and quickly returns inside the range.",
        hypothesis="Late breakout buyers may be trapped after acceptance fails.",
        trade_logic="Enter short on close back inside the range; stop above the sweep high and exit near mid-range.",
        expected_regimes=["normal", "range"],
        invalidation_conditions=["price accepts above the breakout high"],
    )
    pre_review = build_thesis_pre_review(thesis)
    design = build_research_design_draft(thesis, pre_review)

    repository.save_research_thesis(thesis)
    repository.save_thesis_pre_review(pre_review)
    repository.save_research_design_draft(design)
    event = build_event_episode(
        thesis,
        MarketSignal(
            signal_id="signal_repo_event",
            created_at=datetime.utcnow(),
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="5m",
            signal_type=SignalType.FUNDING_OI_EXTREME,
            rank_score=80,
            features={"funding_percentile_30d": 95},
            hypothesis="funding crowding",
            data_sources=["ohlcv", "funding"],
        ),
        design,
    )
    repository.save_event_episode(event)

    assert repository.get_thesis_pre_review(pre_review.pre_review_id) == pre_review
    assert repository.get_research_design_draft(design.design_id) == design
    assert repository.get_event_episode(event.event_id) == event
    assert repository.query_thesis_pre_reviews(thesis_id=thesis.thesis_id) == [pre_review]
    assert repository.query_research_design_drafts(thesis_id=thesis.thesis_id) == [design]
    assert repository.query_event_episodes(thesis_id=thesis.thesis_id) == [event]


def test_funding_thesis_prefers_specialized_short_template() -> None:
    thesis = ResearchThesis(
        thesis_id="thesis_funding_template",
        title="Funding Crowding Fade",
        status=ThesisStatus.DRAFT,
        market_observation="Funding is extreme and OI is high.",
        hypothesis="Crowded longs may exit after failed breakout.",
        trade_logic="Short after failed breakout when funding_percentile_30d >= 90 and OI_percentile_30d >= 75.",
        expected_regimes=["normal"],
        invalidation_conditions=["breakout acceptance"],
    )
    signal = MarketSignal(
        signal_id="signal_funding_template",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="5m",
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=88,
        features={"funding_percentile_30d": 94, "open_interest_percentile_30d": 82},
        hypothesis="funding crowding",
        data_sources=["ohlcv", "funding", "oi"],
    )

    candidates = generate_thesis_strategy_candidates(thesis, signal, count=3)

    assert candidates[0].template_name == "funding_crowding_fade_short"
    assert "can_short = True" in candidates[0].strategy_code
    assert "funding_percentile_30d" in candidates[0].strategy_code
    assert "enter_short" in candidates[0].strategy_code
