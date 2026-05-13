from app.models import PortfolioExposure, PortfolioRiskLimits
from app.services.risk_auditor import audit_portfolio_risk, volatility_adjusted_position_size
from app.storage import QuantRepository


def limits() -> PortfolioRiskLimits:
    return PortfolioRiskLimits(
        max_total_exposure=10_000,
        max_symbol_concentration=0.6,
        max_daily_loss=-500,
        max_strategy_drawdown=-0.2,
        max_correlated_exposure=7_500,
        cooldown_minutes=30,
    )


def exposures() -> list[PortfolioExposure]:
    return [
        PortfolioExposure(
            symbol="BTC/USDT",
            strategy_id="strategy_001",
            notional=4_000,
            correlation_group="crypto_major",
        ),
        PortfolioExposure(
            symbol="ETH/USDT",
            strategy_id="strategy_002",
            notional=3_000,
            correlation_group="crypto_major",
        ),
    ]


def test_portfolio_risk_approves_within_limits() -> None:
    report = audit_portfolio_risk(
        exposures=exposures(),
        limits=limits(),
        daily_pnl=-100,
        strategy_drawdown=-0.05,
        volatility=0.02,
        base_position_size=1_000,
    )

    assert report.approved is True
    assert report.recommended_position_size < 1_000


def test_portfolio_risk_blocks_kill_switch_and_daily_loss() -> None:
    risk_limits = limits().model_copy(update={"kill_switch_enabled": True})

    report = audit_portfolio_risk(
        exposures=exposures(),
        limits=risk_limits,
        daily_pnl=-1_000,
        strategy_drawdown=-0.05,
        volatility=0.02,
        base_position_size=1_000,
    )

    assert report.approved is False
    assert {finding.rule_id for finding in report.findings} >= {"KILL_SWITCH", "MAX_DAILY_LOSS"}
    assert report.recommended_position_size == 0


def test_portfolio_risk_detects_symbol_and_correlated_concentration() -> None:
    risk_limits = limits().model_copy(
        update={"max_symbol_concentration": 0.5, "max_correlated_exposure": 5_000}
    )

    report = audit_portfolio_risk(
        exposures=exposures(),
        limits=risk_limits,
        daily_pnl=0,
        strategy_drawdown=0,
        volatility=0.01,
        base_position_size=1_000,
    )

    assert report.approved is False
    assert {finding.rule_id for finding in report.findings} >= {
        "SYMBOL_CONCENTRATION",
        "CORRELATED_EXPOSURE",
    }


def test_volatility_adjusted_position_size_reduces_size() -> None:
    assert volatility_adjusted_position_size(1_000, 0.05) < 1_000


def test_repository_persists_portfolio_risk_report() -> None:
    repository = QuantRepository()
    report = audit_portfolio_risk(
        exposures=exposures(),
        limits=limits(),
        daily_pnl=0,
        strategy_drawdown=0,
        volatility=0.01,
        base_position_size=1_000,
    )

    repository.save_portfolio_risk_report(report)

    assert repository.get_portfolio_risk_report(report.report_id) == report
