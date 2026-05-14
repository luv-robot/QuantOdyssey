from __future__ import annotations

from app.models import (
    ArenaScoreComponent,
    ArenaScoreReport,
    BacktestReport,
    BacktestValidationReport,
    BaselineComparisonReport,
    ReviewSession,
    RobustnessReport,
)


def build_arena_score(
    backtest: BacktestReport,
    validation: BacktestValidationReport,
    robustness: RobustnessReport,
    baseline: BaselineComparisonReport | None = None,
    review_session: ReviewSession | None = None,
    min_trades: int = 80,
) -> ArenaScoreReport:
    """Build the public Arena V0.1 score from objective research artifacts."""

    components = [
        ArenaScoreComponent(
            name="return_quality",
            score=_return_quality_score(backtest, baseline),
            weight=0.35,
            rationale="Rewards return, profit factor, Sharpe, and baseline advantage.",
        ),
        ArenaScoreComponent(
            name="sample_adequacy",
            score=_sample_adequacy_score(backtest, min_trades=min_trades),
            weight=0.12,
            rationale="Rewards strategies with enough observations to deserve comparison.",
        ),
        ArenaScoreComponent(
            name="drawdown_stability",
            score=_drawdown_stability_score(backtest, robustness),
            weight=0.18,
            rationale="Rewards lower drawdown and stronger robustness evidence.",
        ),
        ArenaScoreComponent(
            name="reproducibility",
            score=_reproducibility_score(validation),
            weight=0.20,
            rationale="Rewards out-of-sample, walk-forward, sensitivity, fee/slippage, and quality checks.",
        ),
        ArenaScoreComponent(
            name="explainability",
            score=_explainability_score(review_session),
            weight=0.10,
            rationale="Rewards clear thesis and failure-understanding evidence without publishing private commentary.",
        ),
    ]
    weighted_score = round(sum(item.score * item.weight for item in components), 2)
    overfit_penalty = _overfit_penalty(validation, robustness, backtest, min_trades=min_trades)
    final_score = _clamp(weighted_score - overfit_penalty)
    labels = _labels(final_score, backtest, validation, robustness)
    findings = _findings(backtest, validation, robustness, baseline, overfit_penalty, min_trades=min_trades)
    return ArenaScoreReport(
        report_id=f"arena_{backtest.strategy_id}_{backtest.backtest_id}",
        strategy_id=backtest.strategy_id,
        backtest_id=backtest.backtest_id,
        final_score=round(final_score, 2),
        weighted_score=weighted_score,
        overfit_penalty=round(overfit_penalty, 2),
        components=components,
        public_metrics={
            "total_return": backtest.total_return,
            "profit_factor": backtest.profit_factor,
            "sharpe": backtest.sharpe,
            "max_drawdown": backtest.max_drawdown,
            "trades": backtest.trades,
            "quality_score": validation.quality_score,
            "robustness_score": robustness.robustness_score,
            "statistical_confidence_score": robustness.statistical_confidence_score,
            "outperformed_best_baseline": None if baseline is None else baseline.outperformed_best_baseline,
        },
        labels=labels,
        findings=findings,
    )


def _return_quality_score(backtest: BacktestReport, baseline: BaselineComparisonReport | None) -> float:
    return_score = _clamp(backtest.total_return / 0.5 * 100)
    profit_factor_score = _clamp(backtest.profit_factor / 2.0 * 100)
    sharpe = backtest.sharpe or 0
    sharpe_score = _clamp((sharpe + 0.5) / 2.5 * 100)
    baseline_bonus = 10 if baseline is not None and baseline.outperformed_best_baseline else 0
    if baseline is not None and not baseline.outperformed_best_baseline:
        baseline_bonus = -10
    return _clamp(return_score * 0.45 + profit_factor_score * 0.3 + sharpe_score * 0.25 + baseline_bonus)


def _sample_adequacy_score(backtest: BacktestReport, min_trades: int) -> float:
    return _clamp(backtest.trades / max(min_trades, 1) * 100)


def _drawdown_stability_score(backtest: BacktestReport, robustness: RobustnessReport) -> float:
    drawdown_abs = abs(backtest.max_drawdown)
    drawdown_score = _clamp((0.25 - drawdown_abs) / 0.25 * 100)
    return _clamp(drawdown_score * 0.6 + robustness.robustness_score * 0.4)


def _reproducibility_score(validation: BacktestValidationReport) -> float:
    checks = [
        validation.walk_forward_passed,
        validation.out_of_sample_passed,
        validation.sensitivity_passed,
        validation.fee_slippage_passed,
        validation.minimum_trades_passed,
    ]
    check_score = sum(1 for item in checks if item) / len(checks) * 100
    return _clamp(check_score * 0.6 + validation.quality_score * 0.4)


def _explainability_score(review_session: ReviewSession | None) -> float:
    if review_session is None:
        return 50
    maturity = review_session.maturity_score
    return _clamp((maturity.thesis_clarity + maturity.failure_understanding) / 2)


def _overfit_penalty(
    validation: BacktestValidationReport,
    robustness: RobustnessReport,
    backtest: BacktestReport,
    min_trades: int,
) -> float:
    penalty = 0.0
    if validation.overfitting_detected:
        penalty += 12
    if not validation.sensitivity_passed:
        penalty += 5
    if not validation.out_of_sample_passed:
        penalty += 4
    if backtest.trades < min_trades:
        penalty += min(5, (min_trades - backtest.trades) / max(min_trades, 1) * 10)
    penalty += max(0, 70 - robustness.statistical_confidence_score) * 0.15
    return min(25, penalty)


def _labels(
    final_score: float,
    backtest: BacktestReport,
    validation: BacktestValidationReport,
    robustness: RobustnessReport,
) -> list[str]:
    labels = []
    if final_score >= 80:
        labels.append("arena_strong")
    elif final_score >= 65:
        labels.append("arena_promising")
    else:
        labels.append("arena_immature")
    if backtest.trades < 80:
        labels.append("low_sample")
    if abs(backtest.max_drawdown) > 0.2:
        labels.append("high_drawdown")
    if validation.overfitting_detected:
        labels.append("overfit_risk")
    if robustness.statistical_confidence_score < 60:
        labels.append("weak_statistical_confidence")
    return labels


def _findings(
    backtest: BacktestReport,
    validation: BacktestValidationReport,
    robustness: RobustnessReport,
    baseline: BaselineComparisonReport | None,
    overfit_penalty: float,
    min_trades: int,
) -> list[str]:
    findings = []
    if baseline is not None and not baseline.outperformed_best_baseline:
        findings.append("Strategy did not outperform the best baseline, so Arena return quality is penalized.")
    if backtest.trades < min_trades:
        findings.append(f"Trade count is below the Arena V0.1 minimum sample target of {min_trades}.")
    if not validation.quality_passed:
        findings.append("Backtest validation quality did not pass the current threshold.")
    if robustness.robustness_score < 65:
        findings.append("Robustness score is weak relative to Arena comparison standards.")
    if overfit_penalty > 0:
        findings.append(f"Overfit penalty applied: {overfit_penalty:.2f}.")
    return findings or ["Arena V0.1 scoring found no major public-score caveats."]


def _clamp(value: float) -> float:
    return max(0, min(100, round(value, 2)))
