from __future__ import annotations

from app.models import BacktestReport, PaperTradingReport, PaperVsBacktestComparison


def compare_paper_vs_backtest(
    backtest: BacktestReport,
    paper_report: PaperTradingReport,
    max_return_delta: float = 0.1,
    max_profit_factor_delta: float = 1.0,
) -> PaperVsBacktestComparison:
    return_delta = paper_report.total_return - backtest.total_return
    profit_factor_delta = paper_report.profit_factor - backtest.profit_factor
    is_consistent = (
        abs(return_delta) <= max_return_delta
        and abs(profit_factor_delta) <= max_profit_factor_delta
        and paper_report.trades > 0
    )
    notes = []
    if not is_consistent:
        notes.append("Paper performance diverged from backtest beyond configured thresholds.")
    if paper_report.trades == 0:
        notes.append("Paper trading produced no trades.")

    return PaperVsBacktestComparison(
        comparison_id=f"paper_vs_backtest_{paper_report.strategy_id}",
        strategy_id=paper_report.strategy_id,
        backtest_total_return=backtest.total_return,
        paper_total_return=paper_report.total_return,
        backtest_profit_factor=backtest.profit_factor,
        paper_profit_factor=paper_report.profit_factor,
        return_delta=round(return_delta, 6),
        profit_factor_delta=round(profit_factor_delta, 6),
        is_consistent=is_consistent,
        notes=notes,
    )
