from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.models import (
    BacktestReport,
    BacktestStatus,
    MarketSignal,
    OhlcvCandle,
    PaperTradingReport,
    PaperVsBacktestComparison,
    StrategyManifest,
    WorkflowRun,
    WorkflowState,
)
from app.services.paper_trading import compare_paper_vs_backtest, run_paper_trading_simulation
from app.storage import QuantRepository


@dataclass(frozen=True)
class PaperTradingFlowResult:
    workflow: WorkflowRun
    report: Optional[PaperTradingReport]
    comparison: Optional[PaperVsBacktestComparison]


def run_paper_trading_flow(
    signal: MarketSignal,
    strategy: StrategyManifest,
    backtest: BacktestReport,
    candles: list[OhlcvCandle],
    repository: Optional[QuantRepository] = None,
) -> PaperTradingFlowResult:
    workflow = WorkflowRun(
        workflow_run_id=f"paper_run_{strategy.strategy_id}",
        signal_id=signal.signal_id,
        strategy_id=strategy.strategy_id,
        state=WorkflowState.HUMAN_REVIEW_REQUIRED,
    )
    if repository is not None:
        repository.save_workflow_run(workflow)

    if backtest.status != BacktestStatus.PASSED:
        workflow = workflow.transition(WorkflowState.RETIRED, error="Backtest did not pass.")
        if repository is not None:
            repository.save_workflow_run(workflow)
        return PaperTradingFlowResult(workflow=workflow, report=None, comparison=None)

    workflow = workflow.transition(WorkflowState.PAPER_TRADING)
    if repository is not None:
        repository.save_workflow_run(workflow)

    paper_result = run_paper_trading_simulation(signal, strategy, candles)
    comparison = compare_paper_vs_backtest(backtest, paper_result.report)

    if repository is not None:
        repository.save_paper_portfolio(paper_result.portfolio)
        for order in paper_result.orders:
            repository.save_paper_order(order)
        for fill in paper_result.fills:
            repository.save_paper_fill(fill)
        for position in paper_result.positions:
            repository.save_paper_position(position)
        repository.save_paper_trading_report(paper_result.report)
        repository.save_paper_vs_backtest_comparison(comparison)

    workflow = workflow.transition(WorkflowState.PAPER_EVALUATION)
    if repository is not None:
        repository.save_workflow_run(workflow)

    final_state = WorkflowState.LIVE_CANDIDATE if comparison.is_consistent else WorkflowState.RETIRED
    workflow = workflow.transition(final_state)
    if repository is not None:
        repository.save_workflow_run(workflow)

    return PaperTradingFlowResult(
        workflow=workflow,
        report=paper_result.report,
        comparison=comparison,
    )
