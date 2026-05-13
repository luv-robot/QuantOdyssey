from __future__ import annotations

from app.models import (
    BacktestReport,
    BacktestValidationReport,
    BaselineComparisonReport,
    MonteCarloBacktestReport,
    RobustnessReport,
)


def evaluate_robustness(
    backtest: BacktestReport,
    validation: BacktestValidationReport,
    monte_carlo: MonteCarloBacktestReport,
    baseline: BaselineComparisonReport,
) -> RobustnessReport:
    checks = {
        "validation_passed": validation.approved,
        "baseline_outperformed": baseline.outperformed_best_baseline,
        "mc_median_positive": monte_carlo.median_return > 0,
        "mc_p05_not_deep_loss": monte_carlo.p05_return > -0.1,
        "mc_loss_probability_acceptable": monte_carlo.probability_of_loss <= 0.35,
        "mc_drawdown_probability_acceptable": monte_carlo.probability_of_20pct_drawdown <= 0.2,
    }
    statistical_confidence_score = _confidence_score(monte_carlo)
    robustness_score = round(
        validation.quality_score * 0.35
        + statistical_confidence_score * 0.35
        + (100 if baseline.outperformed_best_baseline else 0) * 0.2
        + (100 if backtest.trades >= 50 else backtest.trades / 50 * 100) * 0.1,
        2,
    )
    passed = all(checks.values()) and robustness_score >= 65
    findings = [
        f"Statistical confidence score: {statistical_confidence_score}.",
        f"Robustness score: {robustness_score}.",
    ]
    findings.extend(
        f"Check failed: {name}."
        for name, is_passed in checks.items()
        if not is_passed
    )
    if passed:
        findings.append("Strategy passed current robustness criteria.")
    return RobustnessReport(
        report_id=f"robustness_{backtest.backtest_id}",
        strategy_id=backtest.strategy_id,
        source_backtest_id=backtest.backtest_id,
        baseline_report_id=baseline.report_id,
        monte_carlo_report_id=monte_carlo.report_id,
        validation_id=validation.validation_id,
        statistical_confidence_score=statistical_confidence_score,
        robustness_score=robustness_score,
        passed=passed,
        checks=checks,
        findings=findings,
    )


def _confidence_score(monte_carlo: MonteCarloBacktestReport) -> float:
    if monte_carlo.requires_human_confirmation and not monte_carlo.approved_to_run:
        return 0
    median_score = _clamp((monte_carlo.median_return + 0.05) / 0.2 * 100)
    p05_score = _clamp((monte_carlo.p05_return + 0.1) / 0.2 * 100)
    loss_score = _clamp((0.5 - monte_carlo.probability_of_loss) / 0.5 * 100)
    drawdown_score = _clamp((0.3 - monte_carlo.probability_of_20pct_drawdown) / 0.3 * 100)
    return round(
        median_score * 0.25
        + p05_score * 0.25
        + loss_score * 0.3
        + drawdown_score * 0.2,
        2,
    )


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return round(max(low, min(high, value)), 6)
