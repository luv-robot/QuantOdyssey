from datetime import datetime, timedelta

from app.models import (
    BacktestCostModel,
    DataSufficiencyLevel,
    FailedBreakoutUniverseCell,
    FailedBreakoutUniverseReport,
    OhlcvCandle,
    StrategyFamily,
    StrategyScreeningAction,
)
from app.services.harness import (
    build_baseline_implied_regime_report,
    build_data_sufficiency_gate,
    build_regime_coverage_report,
    build_strategy_family_baseline_board,
    build_strategy_family_baseline_boards_by_timeframe,
    decide_strategy_screening_action,
)


def test_baseline_board_includes_btc_dca_with_buy_and_hold_group() -> None:
    candles_by_cell = {
        ("BTC/USDT:USDT", "1h"): _trend_candles("BTC/USDT:USDT"),
        ("BTC/USDT:USDT", "5m"): _trend_candles("BTC/USDT:USDT", count=80),
        ("ETH/USDT:USDT", "1h"): _trend_candles("ETH/USDT:USDT", start_price=1000),
    }

    board = build_strategy_family_baseline_board(candles_by_cell)

    names = [row.strategy_family for row in board.rows]
    assert "cash_no_trade" in names
    assert "passive_btc_buy_and_hold" in names
    assert "passive_btc_dca" in names
    assert "passive_equal_weight_buy_and_hold" in names
    assert "cross_sectional_momentum" in names
    assert "cross_sectional_momentum_long_only" in names
    assert "cross_sectional_momentum_short_only" in names
    assert "time_series_trend" in names
    assert "time_series_trend_long_only" in names
    assert "time_series_trend_short_only" in names
    assert "breakout_trend" in names
    assert "breakout_trend_long_only" in names
    assert "breakout_trend_short_only" in names
    assert "range_mean_reversion_long_only" in names
    assert "range_mean_reversion_short_only" in names
    assert "grid_range" in names
    assert any("DCA BTC" in finding or "DCA" in finding for finding in board.findings)
    assert any("direction_bias" in finding for finding in board.findings)

    passive_btc = next(row for row in board.rows if row.strategy_family == "passive_btc_buy_and_hold")
    equal_weight = next(row for row in board.rows if row.strategy_family == "passive_equal_weight_buy_and_hold")
    trend = next(row for row in board.rows if row.strategy_family == "time_series_trend")
    trend_short = next(row for row in board.rows if row.strategy_family == "time_series_trend_short_only")
    grid = next(row for row in board.rows if row.strategy_family == "grid_range")

    assert passive_btc.display_name == "BTC Buy & Hold"
    assert passive_btc.direction_bias == "long_only"
    assert passive_btc.tested_cell_count == 1
    assert equal_weight.tested_cell_count == 2
    assert trend.direction_bias == "long_short"
    assert trend_short.direction_bias == "short_only"
    assert grid.direction_bias == "long_short"


def test_active_baseline_metrics_use_trade_level_returns_not_cell_returns() -> None:
    candles_by_cell = {
        ("BTC/USDT:USDT", "1h"): _trend_candles("BTC/USDT:USDT", count=400),
        ("ETH/USDT:USDT", "1h"): _trend_candles("ETH/USDT:USDT", start_price=1000, count=400),
    }

    board = build_strategy_family_baseline_board(candles_by_cell)
    trend = next(row for row in board.rows if row.strategy_family == "time_series_trend")
    passive_btc = next(row for row in board.rows if row.strategy_family == "passive_btc_buy_and_hold")

    assert trend.trades > trend.tested_cell_count
    assert trend.profit_factor < 99
    assert trend.max_drawdown < 0
    assert passive_btc.max_drawdown < 0


def test_cross_sectional_momentum_uses_portfolio_curve_not_timeframe_compounding() -> None:
    one_timeframe = {
        ("BTC/USDT:USDT", "1h"): _trend_candles("BTC/USDT:USDT", count=400),
        ("ETH/USDT:USDT", "1h"): _trend_candles("ETH/USDT:USDT", start_price=1000, count=400),
    }
    duplicated_timeframes = {
        **one_timeframe,
        ("BTC/USDT:USDT", "5m"): _trend_candles("BTC/USDT:USDT", count=400),
        ("ETH/USDT:USDT", "5m"): _trend_candles("ETH/USDT:USDT", start_price=1000, count=400),
    }

    single_board = build_strategy_family_baseline_board(one_timeframe)
    duplicated_board = build_strategy_family_baseline_board(duplicated_timeframes)

    single = next(row for row in single_board.rows if row.strategy_family == "cross_sectional_momentum")
    duplicated = next(row for row in duplicated_board.rows if row.strategy_family == "cross_sectional_momentum")

    assert duplicated.return_basis == "equal_weight_portfolio_period_returns"
    assert duplicated.trades == single.trades * 2
    assert duplicated.portfolio_period_count == single.portfolio_period_count
    assert duplicated.total_return == single.total_return


def test_baseline_board_aligns_mixed_timeframes_to_common_window() -> None:
    candles_by_cell = {
        ("BTC/USDT:USDT", "1h"): _trend_candles("BTC/USDT:USDT", count=300),
        ("ETH/USDT:USDT", "1h"): _trend_candles("ETH/USDT:USDT", start_price=1000, count=300),
        ("BTC/USDT:USDT", "1d"): _trend_candles("BTC/USDT:USDT", count=40, interval_hours=24),
        ("ETH/USDT:USDT", "1d"): _trend_candles("ETH/USDT:USDT", start_price=1000, count=40, interval_hours=24),
    }

    board = build_strategy_family_baseline_board(candles_by_cell)

    assert board.is_common_window_aligned is True
    assert board.common_start_at == datetime(2024, 1, 1)
    assert board.common_end_at == datetime(2024, 1, 13, 11)
    assert board.timeframe_scope == "all_common_window"


def test_baseline_boards_by_timeframe_separate_reporting_scope() -> None:
    candles_by_cell = {
        ("BTC/USDT:USDT", "1h"): _trend_candles("BTC/USDT:USDT", count=260),
        ("ETH/USDT:USDT", "1h"): _trend_candles("ETH/USDT:USDT", start_price=1000, count=260),
        ("BTC/USDT:USDT", "1d"): _trend_candles("BTC/USDT:USDT", count=260, interval_hours=24),
    }

    boards = build_strategy_family_baseline_boards_by_timeframe(candles_by_cell)

    assert set(boards) == {"1d", "1h"}
    assert boards["1h"].timeframe_scope == "1h"
    assert boards["1d"].timeframe_scope == "1d"
    assert boards["1h"].timeframes == ["1h"]
    assert boards["1d"].timeframes == ["1d"]


def test_baseline_rows_report_gross_net_and_cost_drag() -> None:
    cost_model = BacktestCostModel(fee_rate=0.001, slippage_bps=5)
    candles_by_cell = {
        ("BTC/USDT:USDT", "1h"): _trend_candles("BTC/USDT:USDT", count=400),
        ("ETH/USDT:USDT", "1h"): _trend_candles("ETH/USDT:USDT", start_price=1000, count=400),
    }

    board = build_strategy_family_baseline_board(candles_by_cell, cost_model=cost_model)
    trend = next(row for row in board.rows if row.strategy_family == "time_series_trend")

    assert board.cost_model.fee_rate == 0.001
    assert trend.gross_return > trend.net_return
    assert trend.total_return == trend.net_return
    assert trend.cost_drag > 0
    assert trend.fee_drag > 0
    assert trend.slippage_drag > 0


def test_baseline_board_excludes_failed_breakout_from_generic_baselines() -> None:
    board = build_strategy_family_baseline_board(
        {("BTC/USDT:USDT", "1h"): _trend_candles("BTC/USDT:USDT")},
        failed_breakout_report=FailedBreakoutUniverseReport(
            report_id="failed_breakout_universe_not_baseline",
            strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
            completed_cells=0,
            min_market_confirmations=1,
        ),
    )

    assert StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value not in [row.strategy_family for row in board.rows]
    assert any("intentionally excluded" in finding for finding in board.findings)


def test_baseline_implied_regime_uses_baseline_performance_as_provisional_signal() -> None:
    candles_by_cell = {
        ("BTC/USDT:USDT", "1h"): _trend_candles("BTC/USDT:USDT", count=260),
        ("ETH/USDT:USDT", "1h"): _trend_candles("ETH/USDT:USDT", start_price=1000, count=260),
    }
    board = build_strategy_family_baseline_board(candles_by_cell)

    report = build_baseline_implied_regime_report(board)

    assert report.source_baseline_board_id == board.board_id
    assert report.regime_label in {
        "beta_trend",
        "directional_trend",
        "mixed_or_transition",
        "range_or_mean_reverting",
        "risk_off_or_low_edge",
    }
    assert 0 <= report.confidence <= 1
    assert "passive_beta" in report.component_scores
    assert report.leading_baselines


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
    interval_hours: int = 1,
) -> list[OhlcvCandle]:
    start = datetime(2024, 1, 1)
    candles: list[OhlcvCandle] = []
    price = start_price
    for index in range(count):
        price *= 1.001 if index < count // 2 else 0.9995
        open_time = start + timedelta(hours=index * interval_hours)
        candles.append(
            OhlcvCandle(
                symbol=symbol,
                interval="1h",
                open_time=open_time,
                close_time=open_time + timedelta(hours=interval_hours),
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
