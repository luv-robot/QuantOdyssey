from __future__ import annotations

from app.models import BacktestReport, BacktestStatus, BacktestValidationReport


def calculate_backtest_quality_metrics(
    report: BacktestReport,
    min_trades: int = 50,
) -> dict[str, float]:
    drawdown_abs = abs(report.max_drawdown)
    sharpe = report.sharpe or 0
    calmar = report.total_return / drawdown_abs if drawdown_abs else max(report.total_return, 0)
    return {
        "profit_factor_score": _clamp(report.profit_factor / 1.8 * 100),
        "sharpe_score": _clamp((sharpe + 1) / 3 * 100),
        "calmar_score": _clamp((calmar + 1) / 3 * 100),
        "return_score": _clamp((report.total_return + 0.1) / 0.4 * 100),
        "drawdown_score": _clamp((0.2 - drawdown_abs) / 0.2 * 100),
        "trade_count_score": _clamp(report.trades / max(min_trades, 1) * 100),
    }


def calculate_backtest_quality_score(metrics: dict[str, float]) -> float:
    weights = {
        "profit_factor_score": 0.25,
        "sharpe_score": 0.2,
        "calmar_score": 0.2,
        "return_score": 0.15,
        "drawdown_score": 0.1,
        "trade_count_score": 0.1,
    }
    return round(sum(metrics.get(key, 0) * weight for key, weight in weights.items()), 2)


def validate_backtest_reliability(
    report: BacktestReport,
    out_of_sample_report: BacktestReport,
    walk_forward_reports: list[BacktestReport],
    sensitivity_reports: list[BacktestReport],
    fee_slippage_report: BacktestReport,
    min_trades: int = 50,
    max_return_drop: float = 0.5,
) -> BacktestValidationReport:
    findings: list[str] = []
    minimum_trades_passed = report.trades >= min_trades
    if not minimum_trades_passed:
        findings.append("Backtest trade count is below minimum threshold.")

    out_of_sample_passed = out_of_sample_report.status == BacktestStatus.PASSED
    if not out_of_sample_passed:
        findings.append("Out-of-sample report failed.")

    walk_forward_passed = bool(walk_forward_reports) and all(
        item.status == BacktestStatus.PASSED for item in walk_forward_reports
    )
    if not walk_forward_passed:
        findings.append("One or more walk-forward windows failed.")

    sensitivity_passed = bool(sensitivity_reports) and all(
        item.total_return >= report.total_return * (1 - max_return_drop)
        for item in sensitivity_reports
    )
    if not sensitivity_passed:
        findings.append("Parameter sensitivity test showed unstable returns.")

    fee_slippage_passed = fee_slippage_report.status == BacktestStatus.PASSED
    if not fee_slippage_passed:
        findings.append("Fee/slippage adjusted report failed.")

    overfitting_detected = (
        report.total_return > 0
        and out_of_sample_report.total_return < report.total_return * (1 - max_return_drop)
    )
    if overfitting_detected:
        findings.append("Out-of-sample return dropped sharply versus in-sample return.")

    quality_metrics = calculate_backtest_quality_metrics(report, min_trades=min_trades)
    quality_score = calculate_backtest_quality_score(quality_metrics)
    quality_passed = quality_score >= 65 and (report.sharpe or 0) >= 0.5
    if not quality_passed:
        findings.append(
            f"Composite backtest quality score {quality_score} is below threshold or Sharpe is weak."
        )

    approved = all(
        [
            report.status == BacktestStatus.PASSED,
            minimum_trades_passed,
            out_of_sample_passed,
            walk_forward_passed,
            sensitivity_passed,
            fee_slippage_passed,
            quality_passed,
            not overfitting_detected,
        ]
    )
    return BacktestValidationReport(
        validation_id=f"validation_{report.backtest_id}",
        strategy_id=report.strategy_id,
        walk_forward_passed=walk_forward_passed,
        out_of_sample_passed=out_of_sample_passed,
        sensitivity_passed=sensitivity_passed,
        fee_slippage_passed=fee_slippage_passed,
        minimum_trades_passed=minimum_trades_passed,
        overfitting_detected=overfitting_detected,
        quality_score=quality_score,
        quality_passed=quality_passed,
        quality_metrics=quality_metrics,
        approved=approved,
        findings=findings or ["Backtest reliability criteria passed."],
    )


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return round(max(low, min(high, value)), 6)
