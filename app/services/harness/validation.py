from __future__ import annotations

import random
from statistics import mean, median, pstdev
from uuid import uuid4

from app.models import (
    FailedBreakoutUniverseReport,
    OhlcvCandle,
    StrategyFamilyMonteCarloReport,
    StrategyFamilyWalkForwardReport,
    StrategyFamilyWalkForwardWindow,
)
from app.services.harness.event_definition import (
    parse_failed_breakout_trial_id,
    simulate_failed_breakout_trial_returns,
)


def run_failed_breakout_walk_forward_validation(
    *,
    universe_report: FailedBreakoutUniverseReport,
    candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]],
    folds: int = 3,
    min_trades_per_window: int = 20,
    min_pass_rate: float = 0.5,
    horizon_hours: int = 2,
    fee_rate: float = 0.001,
) -> StrategyFamilyWalkForwardReport:
    """Replay each best Failed Breakout cell across contiguous time folds."""
    windows: list[StrategyFamilyWalkForwardWindow] = []
    skipped: list[str] = []
    normalized_folds = max(1, folds)

    for cell in universe_report.cells:
        if cell.best_trial_id is None:
            skipped.append(f"{cell.symbol}:{cell.timeframe}:missing_best_trial")
            continue
        candles = candles_by_cell.get((cell.symbol, cell.timeframe))
        if not candles:
            skipped.append(f"{cell.symbol}:{cell.timeframe}:missing_candles")
            continue
        try:
            side = str(parse_failed_breakout_trial_id(cell.best_trial_id)["side"])
        except ValueError:
            skipped.append(f"{cell.symbol}:{cell.timeframe}:unparseable_trial_id")
            continue
        baseline_trial_id = _simple_failed_breakout_trial_id(side)
        for fold_index, fold_candles in enumerate(_split_candles(candles, normalized_folds)):
            if len(fold_candles) < 10:
                skipped.append(f"{cell.symbol}:{cell.timeframe}:fold_{fold_index}:too_short")
                continue
            returns = simulate_failed_breakout_trial_returns(
                fold_candles,
                timeframe=cell.timeframe,
                trial_id=cell.best_trial_id,
                horizon_hours=horizon_hours,
                fee_rate=fee_rate,
            )
            baseline_returns = simulate_failed_breakout_trial_returns(
                fold_candles,
                timeframe=cell.timeframe,
                trial_id=baseline_trial_id,
                horizon_hours=horizon_hours,
                fee_rate=fee_rate,
            )
            stats = _return_stats(returns)
            baseline_stats = _return_stats(baseline_returns)
            beats_baseline = stats["total_return"] > baseline_stats["total_return"]
            passed = (
                len(returns) >= min_trades_per_window
                and stats["total_return"] > 0
                and stats["profit_factor"] > 1
                and beats_baseline
            )
            findings = [
                (
                    f"Fold {fold_index} produced {len(returns)} trade(s); "
                    f"return={stats['total_return']:.4f}, PF={stats['profit_factor']:.2f}."
                ),
                (
                    f"Simple failed-breakout baseline produced {len(baseline_returns)} trade(s); "
                    f"return={baseline_stats['total_return']:.4f}."
                ),
            ]
            if len(returns) < min_trades_per_window:
                findings.append(f"Trade count is below min_trades_per_window={min_trades_per_window}.")
            if not beats_baseline:
                findings.append("Window did not beat the simple failed-breakout baseline.")
            windows.append(
                StrategyFamilyWalkForwardWindow(
                    window_id=f"walk_forward_window_{uuid4().hex[:8]}",
                    symbol=cell.symbol,
                    timeframe=cell.timeframe,
                    trial_id=cell.best_trial_id,
                    fold_index=fold_index,
                    start_at=fold_candles[0].open_time,
                    end_at=fold_candles[-1].close_time,
                    trade_count=len(returns),
                    total_return=round(stats["total_return"], 6),
                    profit_factor=round(stats["profit_factor"], 6),
                    sharpe=stats["sharpe"],
                    max_drawdown=round(stats["max_drawdown"], 6),
                    baseline_total_return=round(baseline_stats["total_return"], 6),
                    baseline_trade_count=len(baseline_returns),
                    beats_baseline=beats_baseline,
                    passed=passed,
                    findings=findings,
                )
            )

    completed_windows = len(windows)
    passed_windows = sum(1 for window in windows if window.passed)
    pass_rate = passed_windows / completed_windows if completed_windows else 0.0
    passed = completed_windows > 0 and pass_rate >= min_pass_rate
    findings = [
        (
            f"Completed {completed_windows} walk-forward window(s); "
            f"{passed_windows} passed with pass_rate={pass_rate:.1%}."
        )
    ]
    if skipped:
        findings.append(f"Skipped {len(skipped)} validation slice(s): {', '.join(skipped)}.")
    if not passed:
        findings.append("Do not promote this strategy family from screening until walk-forward evidence improves.")
    else:
        findings.append("Walk-forward evidence is strong enough to justify the next validation gate.")

    return StrategyFamilyWalkForwardReport(
        report_id=f"strategy_family_walk_forward_{uuid4().hex[:8]}",
        strategy_family=universe_report.strategy_family,
        source_universe_report_id=universe_report.report_id,
        folds=normalized_folds,
        min_trades_per_window=min_trades_per_window,
        completed_windows=completed_windows,
        passed_windows=passed_windows,
        pass_rate=round(pass_rate, 6),
        passed=passed,
        windows=windows,
        findings=findings,
    )


def run_failed_breakout_bootstrap_monte_carlo(
    *,
    universe_report: FailedBreakoutUniverseReport,
    candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]],
    simulations: int = 500,
    horizon_trades: int = 100,
    seed: int | None = None,
    expensive_simulation_threshold: int = 250_000,
    approved_to_run: bool = False,
    min_sampled_trades: int = 50,
    p05_loss_floor: float = -0.1,
    max_probability_of_loss: float = 0.4,
    max_drawdown_floor: float = -0.25,
    horizon_hours: int = 2,
    fee_rate: float = 0.001,
) -> StrategyFamilyMonteCarloReport:
    """Bootstrap best Failed Breakout cell returns to estimate path risk."""
    trade_returns: list[float] = []
    trial_ids: list[str] = []
    skipped: list[str] = []
    for cell in universe_report.cells:
        if cell.best_trial_id is None:
            skipped.append(f"{cell.symbol}:{cell.timeframe}:missing_best_trial")
            continue
        candles = candles_by_cell.get((cell.symbol, cell.timeframe))
        if not candles:
            skipped.append(f"{cell.symbol}:{cell.timeframe}:missing_candles")
            continue
        returns = simulate_failed_breakout_trial_returns(
            candles,
            timeframe=cell.timeframe,
            trial_id=cell.best_trial_id,
            horizon_hours=horizon_hours,
            fee_rate=fee_rate,
        )
        trade_returns.extend(returns)
        trial_ids.append(cell.best_trial_id)

    cost = simulations * horizon_trades
    requires_confirmation = cost > expensive_simulation_threshold
    if requires_confirmation and not approved_to_run:
        return StrategyFamilyMonteCarloReport(
            report_id=f"strategy_family_monte_carlo_{uuid4().hex[:8]}",
            strategy_family=universe_report.strategy_family,
            source_universe_report_id=universe_report.report_id,
            source_trial_ids=sorted(set(trial_ids)),
            simulations=simulations,
            horizon_trades=horizon_trades,
            sampled_trade_count=len(trade_returns),
            expected_return_mean=0,
            median_return=0,
            p05_return=0,
            p95_return=0,
            probability_of_loss=0,
            max_drawdown_median=0,
            max_drawdown_p05=0,
            requires_human_confirmation=True,
            approved_to_run=False,
            passed=False,
            findings=[
                (
                    f"Bootstrap cost {cost} exceeds threshold {expensive_simulation_threshold}; "
                    "human confirmation is required before running."
                )
            ],
        )

    if not trade_returns:
        return StrategyFamilyMonteCarloReport(
            report_id=f"strategy_family_monte_carlo_{uuid4().hex[:8]}",
            strategy_family=universe_report.strategy_family,
            source_universe_report_id=universe_report.report_id,
            source_trial_ids=sorted(set(trial_ids)),
            simulations=simulations,
            horizon_trades=horizon_trades,
            sampled_trade_count=0,
            expected_return_mean=0,
            median_return=0,
            p05_return=0,
            p95_return=0,
            probability_of_loss=0,
            max_drawdown_median=0,
            max_drawdown_p05=0,
            requires_human_confirmation=False,
            approved_to_run=True,
            passed=False,
            findings=["No trade return sample was available for Failed Breakout bootstrap Monte Carlo."],
        )

    rng = random.Random(seed)
    terminal_returns: list[float] = []
    max_drawdowns: list[float] = []
    for _ in range(simulations):
        equity = 1.0
        peak = 1.0
        drawdown = 0.0
        for _ in range(horizon_trades):
            trade_return = rng.choice(trade_returns)
            equity *= 1 + trade_return
            peak = max(peak, equity)
            drawdown = min(drawdown, equity / peak - 1)
        terminal_returns.append(equity - 1)
        max_drawdowns.append(drawdown)

    terminal_sorted = sorted(terminal_returns)
    drawdown_sorted = sorted(max_drawdowns)
    probability_of_loss = sum(item < 0 for item in terminal_returns) / len(terminal_returns)
    p05_return = _quantile(terminal_sorted, 0.05)
    max_drawdown_p05 = _quantile(drawdown_sorted, 0.05)
    passed = (
        len(trade_returns) >= min_sampled_trades
        and median(terminal_returns) > 0
        and p05_return >= p05_loss_floor
        and probability_of_loss <= max_probability_of_loss
        and max_drawdown_p05 >= max_drawdown_floor
    )
    findings = [
        (
            f"Bootstrap sampled {len(trade_returns)} trade return(s) from "
            f"{len(set(trial_ids))} trial id(s)."
        ),
        (
            f"Median terminal return={median(terminal_returns):.4f}, "
            f"p05_return={p05_return:.4f}, probability_of_loss={probability_of_loss:.1%}."
        ),
    ]
    if skipped:
        findings.append(f"Skipped {len(skipped)} cell(s): {', '.join(skipped)}.")
    if not passed:
        findings.append("Path-risk gate failed; treat the universe scan as a research lead, not a watchlist candidate.")
    else:
        findings.append("Path-risk gate passed; candidate can move to review/watchlist discussion.")

    return StrategyFamilyMonteCarloReport(
        report_id=f"strategy_family_monte_carlo_{uuid4().hex[:8]}",
        strategy_family=universe_report.strategy_family,
        source_universe_report_id=universe_report.report_id,
        source_trial_ids=sorted(set(trial_ids)),
        simulations=simulations,
        horizon_trades=horizon_trades,
        sampled_trade_count=len(trade_returns),
        expected_return_mean=round(mean(terminal_returns), 6),
        median_return=round(median(terminal_returns), 6),
        p05_return=round(p05_return, 6),
        p95_return=round(_quantile(terminal_sorted, 0.95), 6),
        probability_of_loss=round(probability_of_loss, 6),
        max_drawdown_median=round(median(max_drawdowns), 6),
        max_drawdown_p05=round(max_drawdown_p05, 6),
        requires_human_confirmation=requires_confirmation,
        approved_to_run=approved_to_run or not requires_confirmation,
        passed=passed,
        findings=findings,
    )


def _split_candles(candles: list[OhlcvCandle], folds: int) -> list[list[OhlcvCandle]]:
    sorted_candles = sorted(candles, key=lambda item: item.open_time)
    if folds <= 1:
        return [sorted_candles]
    fold_size = max(1, len(sorted_candles) // folds)
    slices: list[list[OhlcvCandle]] = []
    for fold_index in range(folds):
        start = fold_index * fold_size
        end = len(sorted_candles) if fold_index == folds - 1 else min(len(sorted_candles), (fold_index + 1) * fold_size)
        if start >= len(sorted_candles):
            break
        slices.append(sorted_candles[start:end])
    return slices


def _simple_failed_breakout_trial_id(side: str) -> str:
    normalized_side = "long" if side == "long" else "short"
    return f"trial_{normalized_side}_rolling_extreme_lb96_lq0_d10_aw6_af0_vz0"


def _return_stats(returns: list[float]) -> dict[str, float | None]:
    if not returns:
        return {
            "total_return": 0.0,
            "profit_factor": 0.0,
            "sharpe": None,
            "max_drawdown": 0.0,
        }
    gross_profit = sum(item for item in returns if item > 0)
    gross_loss = abs(sum(item for item in returns if item < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
    return {
        "total_return": _compound_return(returns),
        "profit_factor": profit_factor,
        "sharpe": _sharpe(returns),
        "max_drawdown": _max_drawdown(returns),
    }


def _compound_return(returns: list[float]) -> float:
    equity = 1.0
    for item in returns:
        equity *= 1 + item
    return equity - 1


def _max_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    for item in returns:
        equity *= 1 + item
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    return drawdown


def _sharpe(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    stdev = pstdev(returns)
    if stdev == 0:
        return None
    return round(mean(returns) / stdev * (len(returns) ** 0.5), 6)


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0
    index = min(len(sorted_values) - 1, max(0, int(round((len(sorted_values) - 1) * q))))
    return sorted_values[index]
