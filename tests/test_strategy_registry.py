from app.models import (
    BacktestReport,
    BacktestStatus,
    PaperEvaluationStatus,
    PaperTradingReport,
    PaperVsBacktestComparison,
    StrategyLifecycleState,
)
from app.services.researcher import generate_mock_strategy
from app.services.strategy_registry import (
    apply_lifecycle_decision,
    detect_decay,
    detect_duplicate_strategy,
    register_strategy,
    should_promote_to_live_candidate,
    should_retire_strategy,
)
from app.storage import QuantRepository
from tests.test_models import sample_signal


def paper_report(
    strategy_id: str = "strategy_001",
    total_return: float = 0.02,
    status: PaperEvaluationStatus = PaperEvaluationStatus.LIVE_CANDIDATE,
    trades: int = 1,
    max_drawdown: float = -0.01,
) -> PaperTradingReport:
    return PaperTradingReport(
        report_id=f"paper_report_{strategy_id}_{total_return}",
        strategy_id=strategy_id,
        portfolio_id=f"paper_{strategy_id}",
        trades=trades,
        win_rate=1 if total_return > 0 else 0,
        total_return=total_return,
        max_drawdown=max_drawdown,
        profit_factor=1.2 if total_return > 0 else 0,
        status=status,
        notes=[],
    )


def passed_backtest(strategy_id: str = "strategy_001") -> BacktestReport:
    return BacktestReport(
        backtest_id=f"backtest_{strategy_id}",
        strategy_id=strategy_id,
        timerange="20240101-20260501",
        trades=80,
        win_rate=0.55,
        profit_factor=1.25,
        max_drawdown=-0.08,
        total_return=0.025,
        status=BacktestStatus.PASSED,
    )


def comparison(strategy_id: str = "strategy_001", consistent: bool = True) -> PaperVsBacktestComparison:
    return PaperVsBacktestComparison(
        comparison_id=f"comparison_{strategy_id}",
        strategy_id=strategy_id,
        backtest_total_return=0.025,
        paper_total_return=0.02,
        backtest_profit_factor=1.25,
        paper_profit_factor=1.2,
        return_delta=-0.005,
        profit_factor_delta=-0.05,
        is_consistent=consistent,
        notes=[] if consistent else ["Diverged."],
    )


def test_register_strategy_creates_registry_entry_and_version() -> None:
    manifest, code = generate_mock_strategy(sample_signal())

    entry, version = register_strategy(manifest, code)

    assert entry.lifecycle_state == StrategyLifecycleState.GENERATED
    assert entry.current_version_id == version.version_id
    assert version.version == 1
    assert len(version.code_hash) == 64


def test_strategy_can_promote_to_live_candidate() -> None:
    manifest, code = generate_mock_strategy(sample_signal())
    entry, _ = register_strategy(manifest, code)

    decision = should_promote_to_live_candidate(
        entry,
        passed_backtest(manifest.strategy_id),
        paper_report(manifest.strategy_id),
        comparison(manifest.strategy_id),
    )
    updated = apply_lifecycle_decision(entry, decision)

    assert decision.approved is True
    assert decision.to_state == StrategyLifecycleState.LIVE_CANDIDATE
    assert updated.lifecycle_state == StrategyLifecycleState.LIVE_CANDIDATE
    assert updated.promoted_at is not None


def test_strategy_promotion_fails_when_paper_diverges() -> None:
    manifest, code = generate_mock_strategy(sample_signal())
    entry, _ = register_strategy(manifest, code)

    decision = should_promote_to_live_candidate(
        entry,
        passed_backtest(manifest.strategy_id),
        paper_report(manifest.strategy_id),
        comparison(manifest.strategy_id, consistent=False),
    )

    assert decision.approved is False
    assert decision.to_state == StrategyLifecycleState.RETIRED


def test_retirement_detects_consecutive_paper_failures() -> None:
    manifest, code = generate_mock_strategy(sample_signal())
    entry, _ = register_strategy(manifest, code)
    reports = [
        paper_report(manifest.strategy_id, -0.01, PaperEvaluationStatus.RETIRED),
        paper_report(manifest.strategy_id, -0.02, PaperEvaluationStatus.RETIRED),
        paper_report(manifest.strategy_id, -0.03, PaperEvaluationStatus.RETIRED),
    ]

    decision = should_retire_strategy(entry, reports)

    assert decision.approved is True
    assert decision.to_state == StrategyLifecycleState.RETIRED


def test_decay_detection_compares_recent_returns_to_baseline() -> None:
    reports = [
        paper_report(total_return=0.12),
        paper_report(total_return=0.10),
        paper_report(total_return=0.01),
        paper_report(total_return=0.0),
        paper_report(total_return=-0.01, status=PaperEvaluationStatus.RETIRED),
    ]

    assert detect_decay(reports, lookback=3, min_return_drop=0.05) is True


def test_duplicate_detection_uses_token_overlap() -> None:
    result = detect_duplicate_strategy(
        "strategy_a",
        "class StrategyA: stoploss = -0.08\nrsi = 14\n",
        "strategy_b",
        "class StrategyB: stoploss = -0.08\nrsi = 14\n",
        threshold=0.5,
    )

    assert result.is_duplicate is True


def test_repository_persists_strategy_registry_assets() -> None:
    repository = QuantRepository()
    manifest, code = generate_mock_strategy(sample_signal())
    entry, version = register_strategy(manifest, code)
    decision = should_promote_to_live_candidate(
        entry,
        passed_backtest(manifest.strategy_id),
        paper_report(manifest.strategy_id),
        comparison(manifest.strategy_id),
    )
    similarity = detect_duplicate_strategy(manifest.strategy_id, code, "other_strategy", code)

    repository.save_strategy_registry_entry(entry)
    repository.save_strategy_version(version)
    repository.save_strategy_lifecycle_decision(decision)
    repository.save_strategy_similarity_result(similarity)

    assert repository.get_strategy_registry_entry(entry.registry_id) == entry
    assert repository.get_strategy_version(version.version_id) == version
