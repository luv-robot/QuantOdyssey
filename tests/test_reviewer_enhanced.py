from app.models import BacktestReport, BacktestStatus, MarketRegime, MonteCarloBacktestReport
from app.services.reviewer import (
    build_enhanced_review_metrics,
    classify_market_regime,
    diagnose_strategy_failure,
    parse_freqtrade_trades,
    review_by_regime,
    summarize_trades,
)
from app.storage import QuantRepository
from tests.test_models import sample_signal
from tests.test_paper_trading import sample_candles


def freqtrade_trade_payload():
    return [
        {
            "trade_id": "trade_1",
            "open_date": "2026-05-10T00:00:00",
            "close_date": "2026-05-10T00:05:00",
            "open_rate": 100,
            "close_rate": 104,
            "amount": 1,
            "profit_abs": 4,
            "profit_pct": 0.04,
            "fee": 0.1,
        },
        {
            "trade_id": "trade_2",
            "open_date": "2026-05-10T00:10:00",
            "close_date": "2026-05-10T00:15:00",
            "open_rate": 104,
            "close_rate": 100,
            "amount": 1,
            "profit_abs": -4,
            "profit_pct": -0.038,
            "fee": 0.1,
        },
    ]


def test_parse_and_summarize_freqtrade_trades() -> None:
    trades = parse_freqtrade_trades("strategy_001", "BTC/USDT", freqtrade_trade_payload())
    summary = summarize_trades("strategy_001", trades)

    assert len(trades) == 2
    assert summary.trades == 2
    assert summary.win_rate == 0.5
    assert summary.total_profit_abs == 0


def test_classify_market_regime_detects_trending_market() -> None:
    regime = classify_market_regime(sample_candles([100, 102, 104, 106, 108]))

    assert regime == MarketRegime.TRENDING


def test_regime_review_explains_losses() -> None:
    trades = parse_freqtrade_trades("strategy_001", "BTC/USDT", freqtrade_trade_payload()[1:])

    review = review_by_regime("strategy_001", trades, MarketRegime.RANGING)

    assert review.total_profit_pct < 0
    assert "lost money" in review.notes[0]


def test_build_enhanced_review_metrics_flags_rank_return_mismatch() -> None:
    signal = sample_signal(rank_score=90)
    trades = parse_freqtrade_trades("strategy_001", "BTC/USDT", freqtrade_trade_payload())

    metrics = build_enhanced_review_metrics(
        signal=signal,
        strategy_id="strategy_001",
        trades=trades,
        candles=sample_candles([100, 101, 102, 103, 104]),
    )

    assert metrics.signal_rank_score == 90
    assert "rank_return_mismatch" in metrics.failure_patterns
    assert metrics.regime_reviews


def test_failure_diagnosis_explains_weak_trade_distribution() -> None:
    signal = sample_signal(rank_score=80)
    trades = parse_freqtrade_trades(
        "strategy_weak",
        "BTC/USDT",
        [
            {
                "trade_id": f"loss_{index}",
                "open_date": f"2026-05-10T00:{index:02d}:00",
                "close_date": f"2026-05-10T00:{index + 1:02d}:00",
                "open_rate": 100,
                "close_rate": 99,
                "amount": 1,
                "profit_abs": -1,
                "profit_pct": -0.01,
                "fee": 0.1,
            }
            for index in range(30)
        ],
    )
    summary = summarize_trades("strategy_weak", trades)
    backtest = BacktestReport(
        backtest_id="backtest_weak",
        strategy_id="strategy_weak",
        timerange="20240101-20260501",
        trades=30,
        win_rate=0,
        profit_factor=0.2,
        max_drawdown=-0.12,
        total_return=-0.3,
        status=BacktestStatus.FAILED,
        error="failed",
    )
    monte_carlo = MonteCarloBacktestReport(
        report_id="mc_weak",
        strategy_id="strategy_weak",
        source_backtest_id="backtest_weak",
        simulations=20,
        horizon_trades=10,
        expected_return_mean=-0.05,
        median_return=-0.04,
        p05_return=-0.1,
        p95_return=0.01,
        probability_of_loss=0.9,
        probability_of_20pct_drawdown=0,
        max_drawdown_median=-0.05,
        max_drawdown_p05=-0.1,
        requires_human_confirmation=False,
        approved_to_run=True,
        notes=[],
    )

    diagnoses = diagnose_strategy_failure(
        signal=signal,
        summary=summary,
        regime=MarketRegime.RANGING,
        backtest=backtest,
        monte_carlo=monte_carlo,
        template_name="volume_momentum",
    )

    categories = {diagnosis.category for diagnosis in diagnoses}
    assert "entry_too_broad" in categories
    assert "payoff_profile_weak" in categories
    assert "monte_carlo_unstable" in categories


def test_enhanced_review_metrics_include_failure_diagnoses() -> None:
    signal = sample_signal(rank_score=90)
    trades = parse_freqtrade_trades("strategy_001", "BTC/USDT", freqtrade_trade_payload()[1:])
    backtest = BacktestReport(
        backtest_id="backtest_001",
        strategy_id="strategy_001",
        timerange="20240101-20260501",
        trades=1,
        win_rate=0,
        profit_factor=0.1,
        max_drawdown=-0.03,
        total_return=-0.038,
        status=BacktestStatus.FAILED,
        error="failed",
    )

    metrics = build_enhanced_review_metrics(
        signal=signal,
        strategy_id="strategy_001",
        trades=trades,
        candles=[],
        backtest=backtest,
        template_name="volume_momentum",
    )

    assert metrics.failure_diagnoses
    assert any("Redesign exits" in lesson or "Block continuation" in lesson for lesson in metrics.reusable_lessons)


def test_repository_persists_trade_and_enhanced_review_assets() -> None:
    repository = QuantRepository()
    signal = sample_signal(rank_score=90)
    trades = parse_freqtrade_trades("strategy_001", "BTC/USDT", freqtrade_trade_payload())
    summary = summarize_trades("strategy_001", trades)
    metrics = build_enhanced_review_metrics(
        signal=signal,
        strategy_id="strategy_001",
        trades=trades,
        candles=sample_candles([100, 101, 102, 103, 104]),
    )

    for trade in trades:
        repository.save_trade(trade)
    repository.save_trade_summary(summary)
    repository.save_enhanced_review_metrics(metrics)

    assert repository.get_trade("trade_1") == trades[0]
    assert repository.get_trade_summary("strategy_001") == summary
    assert repository.get_enhanced_review_metrics("strategy_001") == metrics
