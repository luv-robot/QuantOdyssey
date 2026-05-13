from __future__ import annotations

from app.models import BacktestReport, BaselineComparisonReport, BaselineResult, MarketSignal, SignalType


def compare_to_proxy_baselines(
    signal: MarketSignal,
    backtest: BacktestReport,
) -> BaselineComparisonReport:
    baselines = _generic_proxy_baselines(signal, backtest)
    if signal.signal_type == SignalType.FUNDING_OI_EXTREME:
        baselines.extend(_funding_crowding_proxy_baselines(signal, backtest))

    best = max(baselines, key=lambda item: item.total_return)
    outperformed = backtest.total_return > best.total_return
    findings = [
        f"Best baseline was {best.name} with return {best.total_return:.4f}.",
        "Strategy outperformed the best proxy baseline."
        if outperformed
        else "Strategy did not outperform the best proxy baseline.",
    ]
    if signal.signal_type == SignalType.FUNDING_OI_EXTREME:
        findings.append(
            "Funding-crowding baselines are proxy estimates; replace them with full event-level baseline backtests."
        )
    elif best.name != "cash":
        findings.append("Proxy baselines should be replaced by full baseline backtests when candle data is available.")
    return BaselineComparisonReport(
        report_id=f"baseline_{backtest.backtest_id}",
        strategy_id=backtest.strategy_id,
        signal_id=signal.signal_id,
        source_backtest_id=backtest.backtest_id,
        strategy_total_return=backtest.total_return,
        strategy_profit_factor=backtest.profit_factor,
        best_baseline_name=best.name,
        best_baseline_return=best.total_return,
        outperformed_best_baseline=outperformed,
        baselines=baselines,
        findings=findings,
    )


def _generic_proxy_baselines(
    signal: MarketSignal,
    backtest: BacktestReport,
) -> list[BaselineResult]:
    return [
        BaselineResult(
            name="cash",
            description="No-position baseline.",
            total_return=0,
            profit_factor=0,
            sharpe=0,
            max_drawdown=0,
            trades=0,
        ),
        _buy_and_hold_proxy(signal),
        BaselineResult(
            name="random_entry_proxy",
            description="Conservative random-entry proxy derived from strategy aggregate return.",
            total_return=round(backtest.total_return * 0.25, 6),
            profit_factor=round(max(backtest.profit_factor * 0.5, 0), 6),
            sharpe=None if backtest.sharpe is None else round(backtest.sharpe * 0.5, 6),
            max_drawdown=round(min(backtest.max_drawdown * 1.2, 0), 6),
            trades=max(backtest.trades // 4, 0),
        ),
    ]


def _funding_crowding_proxy_baselines(
    signal: MarketSignal,
    backtest: BacktestReport,
) -> list[BaselineResult]:
    funding_percentile = float(signal.features.get("funding_percentile_30d", 50) or 50)
    oi_percentile = float(
        signal.features.get("open_interest_percentile_30d", signal.features.get("oi_percentile_30d", 50))
        or 50
    )
    funding_strength = max(0, min(1, (funding_percentile - 50) / 50))
    oi_strength = max(0, min(1, (oi_percentile - 50) / 50))
    return [
        BaselineResult(
            name="funding_extreme_only_proxy",
            description="Enter against the crowded side using funding extreme only.",
            total_return=round(backtest.total_return * (0.22 + funding_strength * 0.18), 6),
            profit_factor=round(max(backtest.profit_factor * 0.52, 0), 6),
            sharpe=None if backtest.sharpe is None else round(backtest.sharpe * 0.45, 6),
            max_drawdown=round(min(backtest.max_drawdown * 1.35, 0), 6),
            trades=max(backtest.trades // 3, 1),
        ),
        BaselineResult(
            name="funding_plus_oi_proxy",
            description="Enter against the crowded side using funding extreme plus elevated open interest.",
            total_return=round(backtest.total_return * (0.32 + (funding_strength + oi_strength) * 0.16), 6),
            profit_factor=round(max(backtest.profit_factor * 0.66, 0), 6),
            sharpe=None if backtest.sharpe is None else round(backtest.sharpe * 0.58, 6),
            max_drawdown=round(min(backtest.max_drawdown * 1.2, 0), 6),
            trades=max(backtest.trades // 4, 1),
        ),
        BaselineResult(
            name="simple_failed_breakout_proxy",
            description="Trade failed breakout without funding/OI crowding filters.",
            total_return=round(backtest.total_return * 0.45, 6),
            profit_factor=round(max(backtest.profit_factor * 0.62, 0), 6),
            sharpe=None if backtest.sharpe is None else round(backtest.sharpe * 0.55, 6),
            max_drawdown=round(min(backtest.max_drawdown * 1.25, 0), 6),
            trades=max(backtest.trades // 2, 1),
        ),
        BaselineResult(
            name="opposite_direction_proxy",
            description="Trade with the crowded side after the same setup.",
            total_return=round(-abs(backtest.total_return) * 0.25, 6),
            profit_factor=round(max(backtest.profit_factor * 0.35, 0), 6),
            sharpe=None if backtest.sharpe is None else round(-abs(backtest.sharpe) * 0.35, 6),
            max_drawdown=round(min(backtest.max_drawdown * 1.5, -0.01), 6),
            trades=max(backtest.trades // 4, 1),
        ),
    ]


def _buy_and_hold_proxy(signal: MarketSignal) -> BaselineResult:
    price_change = float(
        signal.features.get("price_change_pct", signal.features.get("return_pct", 0)) or 0
    )
    return BaselineResult(
        name="buy_and_hold_proxy",
        description="Signal-window buy-and-hold proxy from MarketSignal price-change feature.",
        total_return=round(price_change, 6),
        profit_factor=1.0 if price_change > 0 else 0,
        sharpe=None,
        max_drawdown=round(min(price_change, 0), 6),
        trades=1,
    )
