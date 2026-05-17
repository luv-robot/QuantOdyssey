from datetime import datetime

from app.flows.human_research_pipeline import run_human_research_pipeline
from app.models import (
    EnhancedReviewMetrics,
    MarketSignal,
    MarketRegime,
    MonteCarloBacktestConfig,
    RegimeReview,
    ResearchThesis,
    SignalType,
    ThesisStatus,
    TradeSummary,
)
from app.storage import QuantRepository


def test_human_research_pipeline_persists_full_candidate_chain(tmp_path):
    repository = QuantRepository()
    signal = MarketSignal(
        signal_id="signal_pipeline",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="5m",
        signal_type=SignalType.VOLUME_SPIKE,
        rank_score=85,
        features={"volume_zscore": 3.2},
        hypothesis="Volume expansion may confirm continuation.",
        data_sources=["freqtrade:ohlcv"],
    )
    thesis = ResearchThesis(
        thesis_id="thesis_pipeline",
        title="Volume Continuation",
        status=ThesisStatus.READY_FOR_IMPLEMENTATION,
        market_observation="High volume breakout with persistent momentum.",
        hypothesis="Momentum after volume expansion may continue.",
        trade_logic="Enter on volume and RSI confirmation.",
        expected_regimes=["trend continuation"],
        invalidation_conditions=["fails after fee/slippage"],
    )

    result = run_human_research_pipeline(
        thesis,
        signal,
        repository,
        candidate_count=3,
        monte_carlo_config=MonteCarloBacktestConfig(simulations=20, horizon_trades=10),
        backtest_mode="mock",
        strategy_dir=tmp_path,
    )

    assert result.final_status == ThesisStatus.SUPPORTED
    assert result.selected_candidate_id is not None
    assert result.paper_trading_plan is not None
    assert len(result.candidates) == 3
    assert all(item.risk_audit.approved for item in result.candidates)
    assert all(item.backtest is not None for item in result.candidates)
    assert all(item.validation is not None for item in result.candidates)
    assert all(item.experiment_manifest is not None for item in result.candidates)
    assert all(item.baseline_comparison is not None for item in result.candidates)
    assert all(item.robustness_report is not None for item in result.candidates)
    assert all(item.queue_item is not None for item in result.candidates)
    assert all(item.resource_budget is not None for item in result.candidates)
    assert all(item.monte_carlo is not None for item in result.candidates)
    assert len(result.review_sessions) == 3
    assert result.harness_cycle is not None
    assert len(result.research_findings) == 3
    assert result.research_tasks
    assert repository.get_research_thesis("thesis_pipeline").status == ThesisStatus.SUPPORTED
    pre_reviews = repository.query_thesis_pre_reviews(thesis_id="thesis_pipeline")
    assert len(pre_reviews) == 1
    assert pre_reviews[0].questions
    designs = repository.query_research_design_drafts(thesis_id="thesis_pipeline")
    assert len(designs) == 1
    assert designs[0].baseline_set
    event_episodes = repository.query_event_episodes(thesis_id="thesis_pipeline")
    assert len(event_episodes) == 1
    assert event_episodes[0].signal_id == "signal_pipeline"
    manifests = repository.query_experiment_manifests(thesis_id="thesis_pipeline")
    assert len(manifests) == 3
    assert all(item.strategy_code_hash and len(item.strategy_code_hash) == 64 for item in manifests)
    assert all(item.backtest_mode == "mock" for item in manifests)
    assert all(item.data_fingerprint and len(item.data_fingerprint) == 64 for item in manifests)
    baselines = repository.query_baseline_comparisons(signal_id="signal_pipeline")
    assert len(baselines) == 3
    assert all(item.baselines for item in baselines)
    assert all(item.best_baseline_name for item in baselines)
    assert all(item.return_basis == "net_after_costs" for item in baselines)
    assert all(item.cost_model.fee_rate > 0 for item in baselines)
    robustness_reports = repository.query_robustness_reports()
    assert len(robustness_reports) == 3
    assert all(item.robustness_score >= 0 for item in robustness_reports)
    regime_snapshots = repository.query_market_regime_snapshots(signal_id="signal_pipeline")
    assert len(regime_snapshots) == 1
    assert regime_snapshots[0].primary_regime == MarketRegime.TRENDING
    quality = repository.get_data_quality_report("signal_quality_signal_pipeline")
    assert quality is not None
    assert quality.is_usable is True
    assets = repository.query_research_asset_index(thesis_id="thesis_pipeline")
    assert len(assets) == 3
    assert all("human_led_research" in item.tags for item in assets)
    assert all(item.linked_artifacts.get("robustness_report_id") for item in assets)
    queue_items = repository.query_experiment_queue(signal_id="signal_pipeline")
    assert len(queue_items) == 3
    assert {item.status.value for item in queue_items} == {"completed"}
    paper_plans = repository.query_paper_trading_plans(signal_id="signal_pipeline")
    assert len(paper_plans) == 1
    assert paper_plans[0].status.value == "pending_data"
    negative_cases = repository.query_negative_result_cases(signal_id="signal_pipeline")
    assert len(negative_cases) == 2
    assert all(item.reusable_lessons for item in negative_cases)
    resource_budgets = repository.query_resource_budget_reports()
    assert len(resource_budgets) == 3
    assert all(item.approved for item in resource_budgets)
    review_sessions = repository.query_review_sessions(thesis_id="thesis_pipeline")
    assert len(review_sessions) == 3
    assert all(session.scorecard for session in review_sessions)
    assert all(session.scorecard["baseline_return_basis"] == "net_after_costs" for session in review_sessions)
    assert all("cost_fee_rate" in session.scorecard for session in review_sessions)
    assert all(session.maturity_score.overall_score >= 0 for session in review_sessions)
    findings = repository.query_research_findings(thesis_id="thesis_pipeline")
    assert len(findings) == 3
    tasks = repository.query_research_tasks(thesis_id="thesis_pipeline")
    assert tasks
    cycles = repository.query_research_harness_cycles(thesis_id="thesis_pipeline")
    assert len(cycles) == 1
    assert cycles[0].task_ids


def test_human_research_pipeline_gates_expensive_monte_carlo(tmp_path):
    repository = QuantRepository()
    signal = MarketSignal(
        signal_id="signal_expensive_mc",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="5m",
        signal_type=SignalType.VOLUME_SPIKE,
        rank_score=85,
        features={"volume_zscore": 3.2},
        hypothesis="Volume expansion may confirm continuation.",
        data_sources=["freqtrade:ohlcv"],
    )
    thesis = ResearchThesis(
        thesis_id="thesis_expensive_mc",
        title="Volume Continuation",
        status=ThesisStatus.READY_FOR_IMPLEMENTATION,
        market_observation="High volume breakout with persistent momentum.",
        hypothesis="Momentum after volume expansion may continue.",
        trade_logic="Enter on volume and RSI confirmation.",
        expected_regimes=["trend continuation"],
        invalidation_conditions=["fails after fee/slippage"],
    )

    result = run_human_research_pipeline(
        thesis,
        signal,
        repository,
        candidate_count=1,
        monte_carlo_config=MonteCarloBacktestConfig(
            simulations=100,
            horizon_trades=100,
            expensive_simulation_threshold=10,
        ),
        approve_expensive_monte_carlo=False,
        backtest_mode="mock",
        strategy_dir=tmp_path,
    )

    assert result.final_status == ThesisStatus.REJECTED
    assert result.selected_candidate_id is None
    assert result.candidates[0].monte_carlo.requires_human_confirmation
    assert not result.candidates[0].monte_carlo.approved_to_run
    queue_items = repository.query_experiment_queue(signal_id="signal_expensive_mc")
    assert len(queue_items) == 1
    assert queue_items[0].status.value == "awaiting_approval"
    resource_budgets = repository.query_resource_budget_reports()
    assert len(resource_budgets) == 1
    assert resource_budgets[0].requires_human_approval is True
    assert resource_budgets[0].approved is False


def test_human_research_pipeline_injects_historical_lessons(tmp_path):
    repository = QuantRepository()
    signal = MarketSignal(
        signal_id="signal_lessons",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="5m",
        signal_type=SignalType.VOLUME_SPIKE,
        rank_score=85,
        features={"volume_zscore": 3.2},
        hypothesis="Volume expansion may confirm continuation.",
        data_sources=["freqtrade:ohlcv"],
    )
    repository.save_enhanced_review_metrics(
        EnhancedReviewMetrics(
            strategy_id="historical_strategy",
            signal_id=signal.signal_id,
            signal_rank_score=85,
            realized_return=-0.03,
            rank_return_alignment=-0.3,
            trade_summary=TradeSummary(
                strategy_id="historical_strategy",
                trades=25,
                wins=7,
                losses=18,
                win_rate=0.28,
                total_profit_abs=-30,
                total_profit_pct=-0.03,
                average_profit_pct=-0.0012,
                largest_loss_pct=-0.02,
                largest_win_pct=0.01,
            ),
            regime_reviews=[
                RegimeReview(
                    strategy_id="historical_strategy",
                    regime=MarketRegime.TRENDING,
                    trades=25,
                    total_profit_pct=-0.03,
                    win_rate=0.28,
                    notes=["lost money in trend continuation"],
                )
            ],
            failure_patterns=["loss_in_trending"],
            reusable_lessons=["Require stronger trend confirmation before volume entries."],
        )
    )
    thesis = ResearchThesis(
        thesis_id="thesis_lessons",
        title="Volume Continuation Lessons",
        status=ThesisStatus.READY_FOR_IMPLEMENTATION,
        market_observation="High volume breakout with persistent momentum.",
        hypothesis="Momentum after volume expansion may continue.",
        trade_logic="Enter on volume and RSI confirmation.",
        expected_regimes=["trend continuation"],
        invalidation_conditions=["fails after fee/slippage"],
    )

    result = run_human_research_pipeline(
        thesis,
        signal,
        repository,
        candidate_count=1,
        monte_carlo_config=MonteCarloBacktestConfig(simulations=20, horizon_trades=10),
        backtest_mode="mock",
        strategy_dir=tmp_path,
    )

    saved_thesis = repository.get_research_thesis(result.thesis.thesis_id)
    assert saved_thesis is not None
    assert any("Historical lesson:" in item for item in saved_thesis.constraints)
    assert "Require stronger trend confirmation" in result.candidates[0].candidate.manifest.assumptions[-1]


def test_human_research_pipeline_falls_back_to_recent_lessons(tmp_path):
    repository = QuantRepository()
    signal = MarketSignal(
        signal_id="signal_without_exact_history",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="5m",
        signal_type=SignalType.VOLUME_SPIKE,
        rank_score=85,
        features={"volume_zscore": 3.2},
        hypothesis="Volume expansion may confirm continuation.",
        data_sources=["freqtrade:ohlcv"],
    )
    repository.save_enhanced_review_metrics(
        EnhancedReviewMetrics(
            strategy_id="recent_strategy",
            signal_id="different_signal",
            signal_rank_score=85,
            realized_return=-0.03,
            rank_return_alignment=-0.3,
            trade_summary=TradeSummary(
                strategy_id="recent_strategy",
                trades=25,
                wins=7,
                losses=18,
                win_rate=0.28,
                total_profit_abs=-30,
                total_profit_pct=-0.03,
                average_profit_pct=-0.0012,
                largest_loss_pct=-0.02,
                largest_win_pct=0.01,
            ),
            regime_reviews=[],
            failure_patterns=["rank_return_mismatch"],
            reusable_lessons=["Treat recent failures as constraints when exact signal history is absent."],
        )
    )
    thesis = ResearchThesis(
        thesis_id="thesis_recent_lessons",
        title="Volume Continuation Recent Lessons",
        status=ThesisStatus.READY_FOR_IMPLEMENTATION,
        market_observation="High volume breakout with persistent momentum.",
        hypothesis="Momentum after volume expansion may continue.",
        trade_logic="Enter on volume and RSI confirmation.",
        expected_regimes=["trend continuation"],
        invalidation_conditions=["fails after fee/slippage"],
    )

    result = run_human_research_pipeline(
        thesis,
        signal,
        repository,
        candidate_count=1,
        monte_carlo_config=MonteCarloBacktestConfig(simulations=20, horizon_trades=10),
        backtest_mode="mock",
        strategy_dir=tmp_path,
    )

    assert "Treat recent failures" in result.candidates[0].candidate.manifest.assumptions[-1]


def test_human_research_pipeline_prefers_funding_specific_candidate(tmp_path):
    repository = QuantRepository()
    signal = MarketSignal(
        signal_id="signal_funding_specific",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="5m",
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=88,
        features={"funding_percentile_30d": 94, "open_interest_percentile_30d": 82},
        hypothesis="Positive funding and OI crowding may fade after failed breakout.",
        data_sources=["ohlcv", "funding", "oi"],
    )
    thesis = ResearchThesis(
        thesis_id="thesis_funding_specific",
        title="Funding Crowding Fade Short",
        status=ThesisStatus.READY_FOR_IMPLEMENTATION,
        market_observation="Positive funding and high OI indicate crowded longs.",
        hypothesis="Crowded longs may exit after failed breakout.",
        trade_logic=(
            "First test data level = L1 OHLCV + funding + OI. "
            "Short after 3 bars fail above local high."
        ),
        expected_regimes=["normal"],
        invalidation_conditions=["breakout acceptance"],
    )

    result = run_human_research_pipeline(
        thesis,
        signal,
        repository,
        candidate_count=3,
        monte_carlo_config=MonteCarloBacktestConfig(simulations=20, horizon_trades=10),
        backtest_mode="mock",
        strategy_dir=tmp_path,
    )

    selected = next(item for item in result.candidates if item.selected)
    assert selected.candidate.template_name == "funding_crowding_fade_short"
    assert "enter_short" in selected.candidate.strategy_code
