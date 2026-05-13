from __future__ import annotations

from typing import Optional

from app.models import (
    BacktestReport,
    MarketSignal,
    MonteCarloBacktestConfig,
    MonteCarloBacktestReport,
    RiskAuditResult,
    StrategyManifest,
)
from app.services.backtester import run_mock_backtest, run_monte_carlo_backtest
from app.storage import QuantRepository


def run_backtest_flow(
    signal: MarketSignal,
    manifest: StrategyManifest,
    risk_audit: RiskAuditResult,
    repository: Optional[QuantRepository] = None,
) -> Optional[BacktestReport]:
    if not risk_audit.approved:
        return None

    report = run_mock_backtest(signal, manifest)
    if repository is not None:
        repository.save_backtest(report)
    return report


def run_monte_carlo_backtest_flow(
    backtest: BacktestReport,
    config: MonteCarloBacktestConfig | None = None,
    approved_to_run: bool = False,
    repository: Optional[QuantRepository] = None,
) -> MonteCarloBacktestReport:
    report = run_monte_carlo_backtest(
        backtest,
        config=config,
        approved_to_run=approved_to_run,
    )
    if repository is not None:
        repository.save_monte_carlo_backtest(report)
    return report
