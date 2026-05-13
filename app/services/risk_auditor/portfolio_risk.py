from __future__ import annotations

from collections import defaultdict

from app.models import (
    PortfolioExposure,
    PortfolioRiskFinding,
    PortfolioRiskLimits,
    PortfolioRiskReport,
    PortfolioRiskSeverity,
)


def audit_portfolio_risk(
    exposures: list[PortfolioExposure],
    limits: PortfolioRiskLimits,
    daily_pnl: float,
    strategy_drawdown: float,
    volatility: float,
    base_position_size: float,
    in_cooldown: bool = False,
) -> PortfolioRiskReport:
    findings: list[PortfolioRiskFinding] = []
    total_exposure = sum(exposure.notional for exposure in exposures)

    if limits.kill_switch_enabled:
        findings.append(
            PortfolioRiskFinding(
                rule_id="KILL_SWITCH",
                severity=PortfolioRiskSeverity.BLOCK,
                message="Kill switch is enabled.",
            )
        )

    if total_exposure > limits.max_total_exposure:
        findings.append(
            PortfolioRiskFinding(
                rule_id="TOTAL_EXPOSURE",
                severity=PortfolioRiskSeverity.BLOCK,
                message="Total portfolio exposure exceeds limit.",
            )
        )

    if daily_pnl < limits.max_daily_loss:
        findings.append(
            PortfolioRiskFinding(
                rule_id="MAX_DAILY_LOSS",
                severity=PortfolioRiskSeverity.BLOCK,
                message="Daily loss exceeds limit.",
            )
        )

    if strategy_drawdown < limits.max_strategy_drawdown:
        findings.append(
            PortfolioRiskFinding(
                rule_id="STRATEGY_DRAWDOWN",
                severity=PortfolioRiskSeverity.BLOCK,
                message="Strategy drawdown exceeds limit.",
            )
        )

    if in_cooldown:
        findings.append(
            PortfolioRiskFinding(
                rule_id="COOLDOWN",
                severity=PortfolioRiskSeverity.BLOCK,
                message="Strategy is in cooldown period.",
            )
        )

    findings.extend(_symbol_concentration_findings(exposures, total_exposure, limits))
    findings.extend(_correlation_findings(exposures, limits))
    recommended_size = volatility_adjusted_position_size(base_position_size, volatility)
    approved = not any(finding.severity == PortfolioRiskSeverity.BLOCK for finding in findings)

    return PortfolioRiskReport(
        report_id="portfolio_risk_report",
        approved=approved,
        findings=findings,
        recommended_position_size=0 if not approved else recommended_size,
    )


def volatility_adjusted_position_size(base_position_size: float, volatility: float) -> float:
    if volatility <= 0:
        return base_position_size
    return round(base_position_size / (1 + volatility * 10), 6)


def _symbol_concentration_findings(
    exposures: list[PortfolioExposure],
    total_exposure: float,
    limits: PortfolioRiskLimits,
) -> list[PortfolioRiskFinding]:
    if total_exposure == 0:
        return []
    by_symbol: dict[str, float] = defaultdict(float)
    for exposure in exposures:
        by_symbol[exposure.symbol] += exposure.notional
    findings = []
    for symbol, notional in by_symbol.items():
        if notional / total_exposure > limits.max_symbol_concentration:
            findings.append(
                PortfolioRiskFinding(
                    rule_id="SYMBOL_CONCENTRATION",
                    severity=PortfolioRiskSeverity.BLOCK,
                    message=f"{symbol} concentration exceeds limit.",
                )
            )
    return findings


def _correlation_findings(
    exposures: list[PortfolioExposure],
    limits: PortfolioRiskLimits,
) -> list[PortfolioRiskFinding]:
    by_group: dict[str, float] = defaultdict(float)
    for exposure in exposures:
        by_group[exposure.correlation_group] += exposure.notional
    return [
        PortfolioRiskFinding(
            rule_id="CORRELATED_EXPOSURE",
            severity=PortfolioRiskSeverity.BLOCK,
            message=f"{group} correlated exposure exceeds limit.",
        )
        for group, notional in by_group.items()
        if notional > limits.max_correlated_exposure
    ]
