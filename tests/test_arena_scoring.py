from app.models import (
    BacktestReport,
    BacktestStatus,
    BacktestValidationReport,
    BaselineComparisonReport,
    BaselineResult,
    RobustnessReport,
)
from app.services.arena import build_arena_score


def _backtest(**overrides):
    payload = {
        "backtest_id": "bt_001",
        "strategy_id": "strategy_001",
        "timerange": "20240101-20260501",
        "trades": 120,
        "win_rate": 0.54,
        "profit_factor": 1.7,
        "sharpe": 1.4,
        "max_drawdown": -0.08,
        "total_return": 0.28,
        "status": BacktestStatus.PASSED,
    }
    payload.update(overrides)
    return BacktestReport(**payload)


def _validation(**overrides):
    payload = {
        "validation_id": "validation_001",
        "strategy_id": "strategy_001",
        "walk_forward_passed": True,
        "out_of_sample_passed": True,
        "sensitivity_passed": True,
        "fee_slippage_passed": True,
        "minimum_trades_passed": True,
        "overfitting_detected": False,
        "quality_score": 82,
        "quality_passed": True,
        "approved": True,
        "findings": [],
    }
    payload.update(overrides)
    return BacktestValidationReport(**payload)


def _robustness(**overrides):
    payload = {
        "report_id": "robustness_001",
        "strategy_id": "strategy_001",
        "source_backtest_id": "bt_001",
        "baseline_report_id": "baseline_001",
        "monte_carlo_report_id": "mc_001",
        "validation_id": "validation_001",
        "statistical_confidence_score": 86,
        "robustness_score": 80,
        "passed": True,
    }
    payload.update(overrides)
    return RobustnessReport(**payload)


def _baseline(outperformed: bool = True):
    return BaselineComparisonReport(
        report_id="baseline_001",
        strategy_id="strategy_001",
        signal_id="signal_001",
        source_backtest_id="bt_001",
        strategy_total_return=0.28,
        strategy_profit_factor=1.7,
        best_baseline_name="funding_plus_oi_proxy",
        best_baseline_return=0.12,
        outperformed_best_baseline=outperformed,
        baselines=[
            BaselineResult(
                name="funding_plus_oi_proxy",
                description="proxy",
                total_return=0.12,
                profit_factor=1.1,
                sharpe=0.4,
                max_drawdown=-0.1,
                trades=100,
            )
        ],
    )


def test_arena_score_rewards_return_but_splits_robustness_components() -> None:
    report = build_arena_score(_backtest(), _validation(), _robustness(), _baseline())

    components = {item.name: item for item in report.components}
    assert report.final_score > 65
    assert components["return_quality"].weight == 0.35
    assert components["sample_adequacy"].weight == 0.12
    assert components["drawdown_stability"].weight == 0.18
    assert components["reproducibility"].weight == 0.20
    assert components["explainability"].weight == 0.10
    assert report.overfit_penalty == 0
    assert "arena_promising" in report.labels or "arena_strong" in report.labels


def test_arena_score_treats_overfit_as_penalty_not_primary_component() -> None:
    report = build_arena_score(
        _backtest(trades=25, max_drawdown=-0.24),
        _validation(
            out_of_sample_passed=False,
            sensitivity_passed=False,
            minimum_trades_passed=False,
            overfitting_detected=True,
            quality_score=50,
            quality_passed=False,
        ),
        _robustness(statistical_confidence_score=42, robustness_score=45, passed=False),
        _baseline(outperformed=False),
    )

    component_names = {item.name for item in report.components}
    assert "overfit_risk" not in component_names
    assert report.overfit_penalty > 0
    assert report.final_score < report.weighted_score
    assert "overfit_risk" in report.labels
    assert any("Overfit penalty" in finding for finding in report.findings)
