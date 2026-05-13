from datetime import datetime

from app.models import BacktestReport, BacktestStatus, MonteCarloBacktestConfig, TradeRecord
from app.services.backtester import (
    estimate_monte_carlo_cost,
    run_monte_carlo_backtest,
    run_trade_bootstrap_monte_carlo,
)
from app.storage import QuantRepository


def sample_backtest() -> BacktestReport:
    return BacktestReport(
        backtest_id="backtest_strategy_001",
        strategy_id="strategy_001",
        timerange="20250101-20260101",
        trades=100,
        win_rate=0.55,
        profit_factor=1.4,
        sharpe=1.1,
        max_drawdown=-0.08,
        total_return=0.2,
        status=BacktestStatus.PASSED,
    )


def test_monte_carlo_requires_confirmation_for_expensive_runs() -> None:
    config = MonteCarloBacktestConfig(
        simulations=1_000,
        horizon_trades=1_000,
        expensive_simulation_threshold=10_000,
    )

    report = run_monte_carlo_backtest(sample_backtest(), config=config)

    assert estimate_monte_carlo_cost(config) == 1_000_000
    assert report.requires_human_confirmation is True
    assert report.approved_to_run is False
    assert report.probability_of_loss == 0


def test_monte_carlo_runs_when_cost_is_small_and_persists() -> None:
    repository = QuantRepository()
    config = MonteCarloBacktestConfig(simulations=50, horizon_trades=40, seed=7)

    report = run_monte_carlo_backtest(sample_backtest(), config=config)
    repository.save_monte_carlo_backtest(report)

    assert report.requires_human_confirmation is False
    assert report.approved_to_run is True
    assert 0 <= report.probability_of_loss <= 1
    assert repository.get_monte_carlo_backtest(report.report_id) == report


def test_trade_bootstrap_monte_carlo_uses_real_trade_distribution() -> None:
    backtest = sample_backtest()
    trades = [
        TradeRecord(
            trade_id="t1",
            strategy_id=backtest.strategy_id,
            symbol="BTC/USDT",
            opened_at=datetime.utcnow(),
            closed_at=datetime.utcnow(),
            entry_price=100,
            exit_price=104,
            quantity=1,
            profit_abs=4,
            profit_pct=0.04,
            fees=0,
        ),
        TradeRecord(
            trade_id="t2",
            strategy_id=backtest.strategy_id,
            symbol="BTC/USDT",
            opened_at=datetime.utcnow(),
            closed_at=datetime.utcnow(),
            entry_price=100,
            exit_price=98,
            quantity=1,
            profit_abs=-2,
            profit_pct=-0.02,
            fees=0,
        ),
    ]

    report = run_trade_bootstrap_monte_carlo(
        backtest,
        trades,
        MonteCarloBacktestConfig(simulations=50, horizon_trades=10, seed=7),
    )

    assert "trade-level bootstrap" in report.notes[0]
    assert report.simulations == 50
