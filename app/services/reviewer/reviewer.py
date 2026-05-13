from __future__ import annotations

from typing import Optional

from app.models import (
    BacktestReport,
    BacktestStatus,
    MarketSignal,
    ReviewCase,
    ReviewResult,
    RiskAuditResult,
    StrategyManifest,
)


def build_review_case(
    signal: MarketSignal,
    manifest: StrategyManifest,
    risk_result: RiskAuditResult,
    backtest_report: Optional[BacktestReport] = None,
) -> ReviewCase:
    if not risk_result.approved:
        finding_summary = "; ".join(f.message for f in risk_result.findings)
        return ReviewCase(
            case_id=f"case_{manifest.strategy_id}",
            strategy_id=manifest.strategy_id,
            signal_id=signal.signal_id,
            result=ReviewResult.RISK_REJECTED,
            pattern=f"{signal.signal_type.value} strategy was rejected by static risk audit.",
            failure_reason=finding_summary,
            avoid_conditions=["unsafe strategy code", "missing mandatory risk controls"],
            reusable_lessons=["Run static risk audit before any backtest execution."],
        )

    if backtest_report is None:
        raise ValueError("approved strategies require a backtest_report for review")

    passed = backtest_report.status == BacktestStatus.PASSED
    return ReviewCase(
        case_id=f"case_{backtest_report.backtest_id}",
        strategy_id=manifest.strategy_id,
        signal_id=signal.signal_id,
        result=ReviewResult.PASSED if passed else ReviewResult.FAILED,
        pattern=f"{signal.signal_type.value} produced profit_factor={backtest_report.profit_factor}.",
        failure_reason=None if passed else backtest_report.error or "Backtest did not meet pass criteria.",
        avoid_conditions=[] if passed else ["low profit factor", "insufficient trade sample"],
        reusable_lessons=[
            "Keep stoploss and explicit exit logic in generated strategies.",
            "Compare anomaly signals against trend or momentum confirmation before approval.",
        ],
    )
