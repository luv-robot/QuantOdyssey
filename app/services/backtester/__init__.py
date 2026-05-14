from app.services.backtester.baselines import compare_to_event_level_baselines, compare_to_proxy_baselines
from app.services.backtester.freqtrade_cli import (
    build_backtest_command,
    build_backtest_preflight,
    extract_freqtrade_trades,
    find_latest_backtest_result,
    load_freqtrade_trading_mode,
    load_freqtrade_result,
    parse_freqtrade_result_json,
    parse_strategy_name,
    run_freqtrade_backtest,
    run_freqtrade_command,
    strategy_allows_short,
)
from app.services.backtester.monte_carlo import (
    estimate_monte_carlo_cost,
    run_monte_carlo_backtest,
    run_trade_bootstrap_monte_carlo,
)
from app.services.backtester.robustness import evaluate_robustness
from app.services.backtester.mock_backtester import run_mock_backtest
from app.services.backtester.validation import validate_backtest_reliability
from app.services.backtester.validation_suite import run_cross_symbol_validation, run_real_validation_suite

__all__ = [
    "build_backtest_command",
    "build_backtest_preflight",
    "compare_to_proxy_baselines",
    "compare_to_event_level_baselines",
    "extract_freqtrade_trades",
    "find_latest_backtest_result",
    "load_freqtrade_trading_mode",
    "load_freqtrade_result",
    "estimate_monte_carlo_cost",
    "evaluate_robustness",
    "parse_freqtrade_result_json",
    "parse_strategy_name",
    "run_freqtrade_backtest",
    "run_freqtrade_command",
    "strategy_allows_short",
    "run_monte_carlo_backtest",
    "run_trade_bootstrap_monte_carlo",
    "run_mock_backtest",
    "run_cross_symbol_validation",
    "run_real_validation_suite",
    "validate_backtest_reliability",
]
