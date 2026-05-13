from __future__ import annotations

import random
from statistics import mean, median

from app.models import BacktestReport, MonteCarloBacktestConfig, MonteCarloBacktestReport, TradeRecord


def estimate_monte_carlo_cost(config: MonteCarloBacktestConfig) -> int:
    return config.simulations * config.horizon_trades


def run_monte_carlo_backtest(
    backtest: BacktestReport,
    config: MonteCarloBacktestConfig | None = None,
    approved_to_run: bool = False,
) -> MonteCarloBacktestReport:
    config = config or MonteCarloBacktestConfig()
    cost = estimate_monte_carlo_cost(config)
    requires_confirmation = cost > config.expensive_simulation_threshold
    if requires_confirmation and not approved_to_run:
        return MonteCarloBacktestReport(
            report_id=f"monte_carlo_{backtest.backtest_id}",
            strategy_id=backtest.strategy_id,
            source_backtest_id=backtest.backtest_id,
            simulations=config.simulations,
            horizon_trades=config.horizon_trades,
            expected_return_mean=0,
            median_return=0,
            p05_return=0,
            p95_return=0,
            probability_of_loss=0,
            probability_of_20pct_drawdown=0,
            max_drawdown_median=0,
            max_drawdown_p05=0,
            requires_human_confirmation=True,
            approved_to_run=False,
            notes=[
                f"Monte Carlo cost {cost} exceeds threshold "
                f"{config.expensive_simulation_threshold}; human confirmation required."
            ],
        )

    rng = random.Random(config.seed)
    win_return, loss_return = _derive_trade_distribution(backtest)
    terminal_returns: list[float] = []
    max_drawdowns: list[float] = []
    for _ in range(config.simulations):
        equity = 1.0
        peak = 1.0
        max_drawdown = 0.0
        for _ in range(config.horizon_trades):
            trade_return = win_return if rng.random() < backtest.win_rate else loss_return
            equity *= 1 + trade_return
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, (equity - peak) / peak)
        terminal_returns.append(equity - 1)
        max_drawdowns.append(max_drawdown)

    terminal_sorted = sorted(terminal_returns)
    drawdown_sorted = sorted(max_drawdowns)
    return MonteCarloBacktestReport(
        report_id=f"monte_carlo_{backtest.backtest_id}",
        strategy_id=backtest.strategy_id,
        source_backtest_id=backtest.backtest_id,
        simulations=config.simulations,
        horizon_trades=config.horizon_trades,
        expected_return_mean=round(mean(terminal_returns), 6),
        median_return=round(median(terminal_returns), 6),
        p05_return=round(_quantile(terminal_sorted, 0.05), 6),
        p95_return=round(_quantile(terminal_sorted, 0.95), 6),
        probability_of_loss=round(
            sum(item < 0 for item in terminal_returns) / len(terminal_returns),
            6,
        ),
        probability_of_20pct_drawdown=round(
            sum(item <= -0.2 for item in max_drawdowns) / len(max_drawdowns),
            6,
        ),
        max_drawdown_median=round(median(max_drawdowns), 6),
        max_drawdown_p05=round(_quantile(drawdown_sorted, 0.05), 6),
        requires_human_confirmation=requires_confirmation,
        approved_to_run=approved_to_run or not requires_confirmation,
        notes=[
            "Monte Carlo simulation uses a derived two-point trade return distribution.",
            "No trade records were available for bootstrap; use only as a coarse fallback.",
        ],
    )


def run_trade_bootstrap_monte_carlo(
    backtest: BacktestReport,
    trades: list[TradeRecord],
    config: MonteCarloBacktestConfig | None = None,
    approved_to_run: bool = False,
) -> MonteCarloBacktestReport:
    config = config or MonteCarloBacktestConfig()
    if not trades:
        return run_monte_carlo_backtest(backtest, config=config, approved_to_run=approved_to_run)

    cost = estimate_monte_carlo_cost(config)
    requires_confirmation = cost > config.expensive_simulation_threshold
    if requires_confirmation and not approved_to_run:
        return MonteCarloBacktestReport(
            report_id=f"monte_carlo_{backtest.backtest_id}",
            strategy_id=backtest.strategy_id,
            source_backtest_id=backtest.backtest_id,
            simulations=config.simulations,
            horizon_trades=config.horizon_trades,
            expected_return_mean=0,
            median_return=0,
            p05_return=0,
            p95_return=0,
            probability_of_loss=0,
            probability_of_20pct_drawdown=0,
            max_drawdown_median=0,
            max_drawdown_p05=0,
            requires_human_confirmation=True,
            approved_to_run=False,
            notes=[
                f"Trade bootstrap cost {cost} exceeds threshold "
                f"{config.expensive_simulation_threshold}; human confirmation required."
            ],
        )

    rng = random.Random(config.seed)
    trade_returns = [trade.profit_pct for trade in trades]
    terminal_returns: list[float] = []
    max_drawdowns: list[float] = []
    for _ in range(config.simulations):
        equity = 1.0
        peak = 1.0
        max_drawdown = 0.0
        for _ in range(config.horizon_trades):
            trade_return = rng.choice(trade_returns)
            equity *= 1 + trade_return
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, (equity - peak) / peak)
        terminal_returns.append(equity - 1)
        max_drawdowns.append(max_drawdown)

    terminal_sorted = sorted(terminal_returns)
    drawdown_sorted = sorted(max_drawdowns)
    return MonteCarloBacktestReport(
        report_id=f"monte_carlo_{backtest.backtest_id}",
        strategy_id=backtest.strategy_id,
        source_backtest_id=backtest.backtest_id,
        simulations=config.simulations,
        horizon_trades=config.horizon_trades,
        expected_return_mean=round(mean(terminal_returns), 6),
        median_return=round(median(terminal_returns), 6),
        p05_return=round(_quantile(terminal_sorted, 0.05), 6),
        p95_return=round(_quantile(terminal_sorted, 0.95), 6),
        probability_of_loss=round(sum(item < 0 for item in terminal_returns) / len(terminal_returns), 6),
        probability_of_20pct_drawdown=round(
            sum(item <= -0.2 for item in max_drawdowns) / len(max_drawdowns),
            6,
        ),
        max_drawdown_median=round(median(max_drawdowns), 6),
        max_drawdown_p05=round(_quantile(drawdown_sorted, 0.05), 6),
        requires_human_confirmation=requires_confirmation,
        approved_to_run=approved_to_run or not requires_confirmation,
        notes=[
            "Monte Carlo simulation uses trade-level bootstrap from Freqtrade trades.",
            f"Bootstrap sample contains {len(trades)} historical trades.",
        ],
    )


def _derive_trade_distribution(backtest: BacktestReport) -> tuple[float, float]:
    win_rate = min(max(backtest.win_rate, 0.01), 0.99)
    average_trade_return = backtest.total_return / max(backtest.trades, 1)
    loss_return = -max(0.001, abs(average_trade_return) / max(backtest.profit_factor, 0.5))
    win_return = (
        average_trade_return - (1 - win_rate) * loss_return
    ) / win_rate
    return max(win_return, 0.0001), min(loss_return, -0.0001)


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0
    index = min(len(sorted_values) - 1, max(0, int(round((len(sorted_values) - 1) * q))))
    return sorted_values[index]
