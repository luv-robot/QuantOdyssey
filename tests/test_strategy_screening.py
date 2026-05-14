from datetime import datetime, timedelta

from app.models import (
    DataSufficiencyLevel,
    FailedBreakoutUniverseCell,
    FailedBreakoutUniverseReport,
    OhlcvCandle,
    StrategyFamily,
    StrategyScreeningAction,
)
from app.services.harness import (
    build_data_sufficiency_gate,
    build_regime_coverage_report,
    build_strategy_family_baseline_board,
    decide_strategy_screening_action,
)


def test_baseline_board_includes_btc_dca_with_buy_and_hold_group() -> None:
    candles_by_cell = {
        ("BTC/USDT:USDT", "1h"): _trend_candles("BTC/USDT:USDT"),
        ("ETH/USDT:USDT", "1h"): _trend_candles("ETH/USDT:USDT", start_price=1000),
    }

    board = build_strategy_family_baseline_board(candles_by_cell)

    names = [row.strategy_family for row in board.rows]
    assert "passive_btc_buy_and_hold" in names
    assert "passive_btc_dca" in names
    assert any("DCA BTC" in finding or "DCA" in finding for finding in board.findings)


def test_screening_decision_deepens_validation_for_promising_sampled_universe() -> None:
    report = FailedBreakoutUniverseReport(
        report_id="failed_breakout_universe_test",
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
        timeframes=["1h"],
        completed_cells=3,
        min_market_confirmations=2,
        robust_trial_ids=["trial_long_rolling_extreme_lb96_lq0_d25_aw3_af0_vz1p5"],
        best_trial_frequency={"trial_long_rolling_extreme_lb96_lq0_d25_aw3_af0_vz1p5": 2},
        cells=[
            _cell("BTC/USDT:USDT", 109, 0.038, 1.1),
            _cell("ETH/USDT:USDT", 87, 0.216, 1.5),
            _cell("SOL/USDT:USDT", 101, -0.02, 0.98),
        ],
    )
    candles_by_cell = {
        ("BTC/USDT:USDT", "1h"): _trend_candles("BTC/USDT:USDT"),
        ("ETH/USDT:USDT", "1h"): _trend_candles("ETH/USDT:USDT", start_price=1000),
    }
    regime = build_regime_coverage_report(
        candles_by_cell,
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT,
    )
    board = build_strategy_family_baseline_board(candles_by_cell, failed_breakout_report=report)
    gate = build_data_sufficiency_gate(
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT,
        available_level=DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION,
    )

    decision = decide_strategy_screening_action(
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT,
        universe_report=report,
        regime_coverage=regime,
        baseline_board=board,
        data_gate=gate,
    )

    assert decision.action == StrategyScreeningAction.DEEPEN_VALIDATION
    assert {task.task_type.value for task in decision.next_tasks} == {"walk_forward_test", "monte_carlo_test"}


def test_screening_decision_upgrades_data_for_positive_but_under_sampled_failed_breakout() -> None:
    report = FailedBreakoutUniverseReport(
        report_id="failed_breakout_universe_sparse",
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        completed_cells=3,
        min_market_confirmations=2,
        cells=[
            _cell("BTC/USDT:USDT", 49, 0.011, 1.1),
            _cell("ETH/USDT:USDT", 21, 0.043, 1.7),
            _cell("SOL/USDT:USDT", 34, 0.051, 1.4),
        ],
    )
    gate = build_data_sufficiency_gate(
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT,
        available_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
    )

    decision = decide_strategy_screening_action(
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT,
        universe_report=report,
        regime_coverage=None,
        baseline_board=None,
        data_gate=gate,
    )

    assert decision.action == StrategyScreeningAction.UPGRADE_DATA
    assert decision.next_tasks[0].required_data_level == DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION


def _cell(symbol: str, trades: int, return_: float, pf: float) -> FailedBreakoutUniverseCell:
    return FailedBreakoutUniverseCell(
        report_id=f"report_{symbol}",
        symbol=symbol,
        timeframe="1h",
        completed_trials=32,
        robust_trial_count=1 if return_ > 0 and trades >= 80 else 0,
        simple_failed_breakout_total_return=-0.1,
        simple_failed_breakout_trade_count=200,
        best_trial_id="trial_long_rolling_extreme_lb96_lq0_d25_aw3_af0_vz1p5",
        best_trial_trade_count=trades,
        best_trial_total_return=return_,
        best_trial_profit_factor=pf,
    )


def _trend_candles(
    symbol: str,
    *,
    start_price: float = 100,
    count: int = 180,
) -> list[OhlcvCandle]:
    start = datetime(2024, 1, 1)
    candles: list[OhlcvCandle] = []
    price = start_price
    for index in range(count):
        price *= 1.001 if index < count // 2 else 0.9995
        open_time = start + timedelta(hours=index)
        candles.append(
            OhlcvCandle(
                symbol=symbol,
                interval="1h",
                open_time=open_time,
                close_time=open_time + timedelta(hours=1),
                open=price * 0.999,
                high=price * 1.003,
                low=price * 0.997,
                close=price,
                volume=1000 + index,
                quote_volume=(1000 + index) * price,
                trade_count=100 + index,
                raw=[],
            )
        )
    return candles
