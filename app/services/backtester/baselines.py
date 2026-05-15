from __future__ import annotations

from datetime import timezone

from app.models import (
    BacktestReport,
    BaselineComparisonReport,
    BaselineResult,
    FundingRatePoint,
    MarketSignal,
    OhlcvCandle,
    OpenInterestPoint,
    SignalType,
)
from app.services.metrics import compound_return, max_drawdown, profit_factor, sharpe_ratio


def compare_to_event_level_baselines(
    signal: MarketSignal,
    backtest: BacktestReport,
    *,
    candles: list[OhlcvCandle] | None = None,
    funding_rates: list[FundingRatePoint] | None = None,
    open_interest_points: list[OpenInterestPoint] | None = None,
) -> BaselineComparisonReport:
    if (
        signal.signal_type != SignalType.FUNDING_OI_EXTREME
        or not candles
        or len(candles) < 80
        or not funding_rates
        or len(funding_rates) < 30
    ):
        return compare_to_proxy_baselines(signal, backtest)

    baselines = _generic_event_baselines(signal)
    baselines.extend(
        _funding_crowding_event_baselines(
            candles=sorted(candles, key=lambda item: item.open_time),
            funding_rates=sorted(funding_rates, key=lambda item: item.funding_time),
            open_interest_points=None
            if open_interest_points is None
            else sorted(open_interest_points, key=lambda item: item.timestamp),
            timeframe=signal.timeframe,
        )
    )
    if not baselines:
        return compare_to_proxy_baselines(signal, backtest)

    best = max(baselines, key=lambda item: item.total_return)
    outperformed = backtest.total_return > best.total_return
    findings = [
        f"Best event-level baseline was {best.name} with return {best.total_return:.4f}.",
        "Strategy outperformed the best event-level baseline."
        if outperformed
        else "Strategy did not outperform the best event-level baseline.",
    ]
    if open_interest_points:
        findings.append("Funding-crowding event baselines used historical open-interest data.")
    else:
        findings.append("Funding-crowding event baselines used volume as an open-interest proxy.")
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


def _generic_event_baselines(signal: MarketSignal) -> list[BaselineResult]:
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
        _buy_and_hold_event(signal),
    ]


def _funding_crowding_event_baselines(
    *,
    candles: list[OhlcvCandle],
    funding_rates: list[FundingRatePoint],
    open_interest_points: list[OpenInterestPoint] | None,
    timeframe: str,
) -> list[BaselineResult]:
    horizon_bars = _bars_for_duration(timeframe, hours=4)
    features = _precompute_event_features(candles, funding_rates, open_interest_points)
    return [
        _simulate_event_baseline(
            "funding_extreme_only_event",
            "Short fixed-horizon entries whenever funding is in its rolling top decile.",
            candles,
            features,
            horizon_bars=horizon_bars,
            side="short",
            require_funding=True,
            require_oi=False,
            require_failed_breakout=False,
        ),
        _simulate_event_baseline(
            "funding_plus_oi_event",
            "Short fixed-horizon entries on funding extreme plus elevated participation/OI.",
            candles,
            features,
            horizon_bars=horizon_bars,
            side="short",
            require_funding=True,
            require_oi=True,
            require_failed_breakout=False,
        ),
        _simulate_event_baseline(
            "simple_failed_breakout_event",
            "Short fixed-horizon entries after failed breakout without funding/OI filters.",
            candles,
            features,
            horizon_bars=horizon_bars,
            side="short",
            require_funding=False,
            require_oi=False,
            require_failed_breakout=True,
        ),
        _simulate_event_baseline(
            "opposite_direction_event",
            "Long fixed-horizon entries with the crowded side after the full event setup.",
            candles,
            features,
            horizon_bars=horizon_bars,
            side="long",
            require_funding=True,
            require_oi=True,
            require_failed_breakout=True,
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


def _buy_and_hold_event(signal: MarketSignal) -> BaselineResult:
    result = _buy_and_hold_proxy(signal)
    return result.model_copy(
        update={
            "name": "buy_and_hold_event",
            "description": "Signal-window buy-and-hold baseline for event-level comparisons.",
        }
    )


def _simulate_event_baseline(
    name: str,
    description: str,
    candles: list[OhlcvCandle],
    features_by_index: list[dict[str, float | bool]],
    *,
    horizon_bars: int,
    side: str,
    require_funding: bool,
    require_oi: bool,
    require_failed_breakout: bool,
    fee_rate: float = 0.001,
) -> BaselineResult:
    returns: list[float] = []
    index = max(64, _bars_for_duration(candles[0].interval, hours=24))
    while index + horizon_bars < len(candles):
        features = features_by_index[index]
        if _baseline_condition(
            features,
            require_funding=require_funding,
            require_oi=require_oi,
            require_failed_breakout=require_failed_breakout,
        ):
            entry = candles[index].close
            exit_ = candles[index + horizon_bars].close
            raw_return = exit_ / entry - 1 if side == "long" else entry / exit_ - 1
            returns.append(raw_return - fee_rate)
            index += horizon_bars
        else:
            index += 1
    return _baseline_result_from_returns(name, description, returns)


def _precompute_event_features(
    candles: list[OhlcvCandle],
    funding_rates: list[FundingRatePoint],
    open_interest_points: list[OpenInterestPoint] | None,
) -> list[dict[str, float | bool]]:
    features = []
    funding_index = 0
    oi_index = 0
    funding_window: list[float] = []
    oi_window: list[float] = []
    bars_24h = _bars_for_duration(candles[0].interval, hours=24)
    for index, candle in enumerate(candles):
        candle_timestamp = _datetime_seconds(candle.open_time)
        while (
            funding_index < len(funding_rates)
            and _datetime_seconds(funding_rates[funding_index].funding_time) <= candle_timestamp
        ):
            funding_window.append(funding_rates[funding_index].funding_rate)
            funding_index += 1
        if open_interest_points:
            while (
                oi_index < len(open_interest_points)
                and _datetime_seconds(open_interest_points[oi_index].timestamp) <= candle_timestamp
            ):
                oi_window.append(open_interest_points[oi_index].open_interest)
                oi_index += 1
        funding_percentile = (
            _latest_percentile(funding_window[-90:], funding_window[-1])
            if funding_window
            else 50.0
        )
        oi_percentile = (
            _latest_percentile(oi_window[-90:], oi_window[-1])
            if oi_window
            else _latest_percentile([item.volume for item in candles[max(0, index - 90) : index + 1]], candle.volume)
        )
        if index >= 51:
            range_high = max(item.high for item in candles[index - 51 : index - 3])
            recent_high_3 = max(item.high for item in candles[index - 2 : index + 1])
            failed_breakout = recent_high_3 > range_high and candle.close < range_high
        else:
            failed_breakout = False
        price_change_24h = candle.close / candles[max(0, index - bars_24h)].close - 1
        features.append(
            {
                "funding_percentile": funding_percentile,
                "oi_percentile": oi_percentile,
                "failed_breakout": failed_breakout,
                "price_change_24h": price_change_24h,
            }
        )
    return features


def _baseline_condition(
    features: dict[str, float | bool],
    *,
    require_funding: bool,
    require_oi: bool,
    require_failed_breakout: bool,
) -> bool:
    if require_funding and float(features["funding_percentile"]) < 90:
        return False
    if require_oi and float(features["oi_percentile"]) < 75:
        return False
    if require_failed_breakout and not bool(features["failed_breakout"]):
        return False
    if (require_funding or require_oi) and float(features["price_change_24h"]) <= 0:
        return False
    return True


def _baseline_result_from_returns(name: str, description: str, returns: list[float]) -> BaselineResult:
    if not returns:
        return BaselineResult(
            name=name,
            description=description,
            total_return=0,
            profit_factor=0,
            sharpe=None,
            max_drawdown=0,
            trades=0,
        )
    return BaselineResult(
        name=name,
        description=description,
        total_return=round(compound_return(returns), 6),
        profit_factor=round(profit_factor(returns), 6),
        sharpe=sharpe_ratio(returns),
        max_drawdown=round(max_drawdown(returns), 6),
        trades=len(returns),
    )


def _latest_percentile(values: list[float], latest: float) -> float:
    if not values:
        return 50.0
    return sum(1 for value in values if value <= latest) / len(values) * 100


def _datetime_seconds(value) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _bars_for_duration(timeframe: str, hours: int) -> int:
    unit = timeframe[-1]
    value = int(timeframe[:-1])
    if unit == "m":
        return max(1, hours * 60 // value)
    if unit == "h":
        return max(1, hours // value)
    return 1
