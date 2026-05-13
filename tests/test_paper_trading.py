from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.flows import run_paper_trading_flow
from app.models import (
    BacktestReport,
    BacktestStatus,
    OhlcvCandle,
    PaperEvaluationStatus,
    PaperOrder,
    PaperOrderSide,
    PaperOrderStatus,
    PaperPosition,
    PaperPositionStatus,
    WorkflowState,
)
from app.services.paper_trading import compare_paper_vs_backtest, run_paper_trading_simulation
from app.storage import QuantRepository
from tests.test_models import sample_manifest, sample_signal


def sample_candles(prices: list[float]) -> list[OhlcvCandle]:
    base = datetime(2026, 5, 10, tzinfo=timezone.utc)
    candles = []
    for index, price in enumerate(prices):
        candles.append(
            OhlcvCandle(
                symbol="BTC/USDT",
                interval="5m",
                open_time=base + timedelta(minutes=5 * index),
                close_time=base + timedelta(minutes=5 * index + 4),
                open=price,
                high=price + 1,
                low=price - 1,
                close=price,
                volume=100 + index,
                quote_volume=(100 + index) * price,
                trade_count=100,
                raw=[],
            )
        )
    return candles


def passed_backtest(strategy_id: str = "strategy_001") -> BacktestReport:
    return BacktestReport(
        backtest_id=f"backtest_{strategy_id}",
        strategy_id=strategy_id,
        timerange="20240101-20260501",
        trades=100,
        win_rate=0.55,
        profit_factor=1.1,
        sharpe=1.2,
        max_drawdown=-0.05,
        total_return=0.01,
        status=BacktestStatus.PASSED,
    )


def test_rejected_paper_order_requires_reason() -> None:
    with pytest.raises(ValidationError):
        PaperOrder(
            order_id="order_001",
            strategy_id="strategy_001",
            symbol="BTC/USDT",
            side=PaperOrderSide.BUY,
            quantity=1,
            requested_price=100,
            status=PaperOrderStatus.REJECTED,
        )


def test_closed_paper_position_requires_exit_price() -> None:
    with pytest.raises(ValidationError):
        PaperPosition(
            position_id="position_001",
            strategy_id="strategy_001",
            symbol="BTC/USDT",
            quantity=1,
            entry_price=100,
            status=PaperPositionStatus.CLOSED,
        )


def test_paper_trading_simulation_generates_orders_fills_positions_and_report() -> None:
    result = run_paper_trading_simulation(
        signal=sample_signal(),
        strategy=sample_manifest(),
        candles=sample_candles([100, 102, 104, 106, 108, 110]),
    )

    assert len(result.orders) == 2
    assert len(result.fills) == 2
    assert result.positions[0].status == PaperPositionStatus.CLOSED
    assert result.report.trades == 1
    assert result.report.status == PaperEvaluationStatus.LIVE_CANDIDATE
    assert result.portfolio.equity > result.portfolio.starting_cash


def test_paper_vs_backtest_comparison_flags_consistency() -> None:
    paper = run_paper_trading_simulation(
        signal=sample_signal(),
        strategy=sample_manifest(),
        candles=sample_candles([100, 102, 104, 106, 108, 110]),
    )

    comparison = compare_paper_vs_backtest(passed_backtest(), paper.report)

    assert comparison.is_consistent is True
    assert comparison.return_delta != 0


def test_paper_trading_flow_persists_assets_and_promotes_consistent_strategy() -> None:
    repository = QuantRepository()
    signal = sample_signal()
    strategy = sample_manifest()

    result = run_paper_trading_flow(
        signal=signal,
        strategy=strategy,
        backtest=passed_backtest(strategy.strategy_id),
        candles=sample_candles([100, 102, 104, 106, 108, 110]),
        repository=repository,
    )

    assert result.workflow.state == WorkflowState.LIVE_CANDIDATE
    assert result.report is not None
    assert result.comparison is not None
    assert repository.get_paper_trading_report(result.report.report_id) == result.report
    assert repository.get_paper_vs_backtest_comparison(result.comparison.comparison_id) == result.comparison
    assert repository.get_workflow_run(result.workflow.workflow_run_id).state == WorkflowState.LIVE_CANDIDATE


def test_paper_trading_flow_retires_failed_backtest_without_paper_orders() -> None:
    failed = passed_backtest()
    failed = failed.model_copy(update={"status": BacktestStatus.FAILED, "error": "Failed criteria."})

    result = run_paper_trading_flow(
        signal=sample_signal(),
        strategy=sample_manifest(),
        backtest=failed,
        candles=sample_candles([100, 101]),
    )

    assert result.workflow.state == WorkflowState.RETIRED
    assert result.report is None
    assert result.comparison is None
