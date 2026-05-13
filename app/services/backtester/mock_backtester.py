from __future__ import annotations

from app.models import BacktestReport, BacktestStatus, MarketSignal, StrategyManifest


def run_mock_backtest(
    signal: MarketSignal,
    manifest: StrategyManifest,
    timerange: str = "20240101-20260501",
) -> BacktestReport:
    profit_factor = round(0.8 + signal.rank_score / 100, 2)
    max_drawdown = -round(max(0.05, (100 - signal.rank_score) / 300), 3)
    trades = max(20, int(signal.rank_score * 1.4))
    status = (
        BacktestStatus.PASSED
        if profit_factor >= 1.2 and max_drawdown >= -0.15 and trades >= 50
        else BacktestStatus.FAILED
    )

    return BacktestReport(
        backtest_id=f"backtest_{manifest.strategy_id}",
        strategy_id=manifest.strategy_id,
        timerange=timerange,
        trades=trades,
        win_rate=round(min(0.7, 0.35 + signal.rank_score / 300), 2),
        profit_factor=profit_factor,
        sharpe=round(profit_factor - 0.2, 2),
        max_drawdown=max_drawdown,
        total_return=round((profit_factor - 1) / 3, 3),
        status=status,
        error=None if status == BacktestStatus.PASSED else "Mock pass criteria were not met.",
    )
