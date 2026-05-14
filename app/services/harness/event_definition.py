from __future__ import annotations

from datetime import timezone
from statistics import mean, pstdev
from uuid import uuid4

from app.models import (
    EventDefinitionSensitivityReport,
    EventDefinitionSensitivityTrial,
    EventDefinitionUniverseCell,
    EventDefinitionUniverseReport,
    FailedBreakoutSensitivityReport,
    FailedBreakoutSensitivityTrial,
    FailedBreakoutUniverseCell,
    FailedBreakoutUniverseReport,
    FundingRatePoint,
    OhlcvCandle,
    OpenInterestPoint,
    ResearchTask,
    StrategyFamily,
)


def build_event_definition_universe_report(
    *,
    task: ResearchTask | None,
    reports: list[EventDefinitionSensitivityReport],
    skipped_cells: list[str] | None = None,
    min_market_confirmations: int = 2,
    min_trade_count: int = 20,
) -> EventDefinitionUniverseReport:
    """Aggregate per-market event-definition reports into a cross-market stability view."""
    skipped_cells = skipped_cells or []
    cells = [_cell_from_report(report) for report in reports]
    robust_counts: dict[str, int] = {}
    best_counts: dict[str, int] = {}
    for report in reports:
        if report.best_trial is not None:
            best_counts[report.best_trial.trial_id] = best_counts.get(report.best_trial.trial_id, 0) + 1
        for trial in report.trials:
            if (
                trial.trade_count >= min_trade_count
                and trial.total_return > 0
                and trial.profit_factor > 1
                and trial.beats_funding_only
            ):
                robust_counts[trial.trial_id] = robust_counts.get(trial.trial_id, 0) + 1
    robust_trial_ids = sorted(
        [trial_id for trial_id, count in robust_counts.items() if count >= min_market_confirmations]
    )
    symbols = sorted({report.symbol for report in reports})
    timeframes = sorted({report.timeframe for report in reports})
    findings = _universe_findings(
        reports=reports,
        cells=cells,
        skipped_cells=skipped_cells,
        robust_trial_ids=robust_trial_ids,
        robust_counts=robust_counts,
        best_counts=best_counts,
        min_market_confirmations=min_market_confirmations,
    )
    return EventDefinitionUniverseReport(
        report_id=f"event_definition_universe_{uuid4().hex[:8]}",
        task_id=None if task is None else task.task_id,
        thesis_id=None if task is None else task.thesis_id,
        signal_id=None if task is None else task.signal_id,
        strategy_family=StrategyFamily.FUNDING_CROWDING_FADE.value,
        symbols=symbols,
        timeframes=timeframes,
        completed_cells=len(reports),
        skipped_cells=skipped_cells,
        min_market_confirmations=min_market_confirmations,
        robust_trial_ids=robust_trial_ids,
        best_trial_frequency=dict(sorted(best_counts.items(), key=lambda item: (-item[1], item[0]))),
        cells=cells,
        child_report_ids=[report.report_id for report in reports],
        findings=findings,
    )


def run_funding_crowding_event_definition_sensitivity(
    *,
    task: ResearchTask | None,
    candles: list[OhlcvCandle],
    funding_rates: list[FundingRatePoint],
    open_interest_points: list[OpenInterestPoint] | None,
    symbol: str,
    timeframe: str,
    funding_thresholds: tuple[float, ...] = (90, 95, 97.5),
    oi_thresholds: tuple[float, ...] = (75, 85, 90),
    failed_breakout_windows: tuple[int, ...] = (3, 6, 12),
    oi_retreat_thresholds: tuple[float, ...] = (0, 0.005, 0.01, 0.02),
    horizon_hours: int = 4,
    min_trade_count: int = 20,
    fee_rate: float = 0.001,
    max_trials: int = 200,
) -> EventDefinitionSensitivityReport:
    """Run a bounded event-definition grid for the short Funding Crowding Fade thesis."""
    sorted_candles = sorted(candles, key=lambda item: item.open_time)
    sorted_funding = sorted(funding_rates, key=lambda item: item.funding_time)
    sorted_oi = [] if open_interest_points is None else sorted(open_interest_points, key=lambda item: item.timestamp)
    data_warnings: list[str] = []

    if len(sorted_candles) < 80:
        data_warnings.append("fewer_than_80_candles")
    if len(sorted_funding) < 30:
        data_warnings.append("fewer_than_30_funding_points")
    if sorted_oi:
        first_oi = _datetime_seconds(sorted_oi[0].timestamp)
        last_oi = _datetime_seconds(sorted_oi[-1].timestamp)
        before_count = len(sorted_candles)
        sorted_candles = [
            candle
            for candle in sorted_candles
            if first_oi <= _datetime_seconds(candle.open_time) <= last_oi
        ]
        if len(sorted_candles) < before_count:
            data_warnings.append("candles_restricted_to_open_interest_overlap")
    else:
        data_warnings.append("historical_open_interest_missing_volume_proxy_used")

    horizon_bars = _bars_for_duration(timeframe, hours=horizon_hours)
    features = _precompute_features(sorted_candles, sorted_funding, sorted_oi, failed_breakout_windows, timeframe)
    funding_only_returns = _simulate_returns(
        sorted_candles,
        features,
        horizon_bars=horizon_bars,
        fee_rate=fee_rate,
        predicate=lambda item: item["funding_percentile"] >= 90 and item["price_change_24h"] > 0,
    )
    funding_only_stats = _stats_from_returns(funding_only_returns)

    trials: list[EventDefinitionSensitivityTrial] = []
    search_budget = (
        len(funding_thresholds)
        * len(oi_thresholds)
        * len(failed_breakout_windows)
        * len(oi_retreat_thresholds)
    )
    completed = 0
    for funding_threshold in funding_thresholds:
        for oi_threshold in oi_thresholds:
            for failed_breakout_window in failed_breakout_windows:
                for oi_retreat_threshold in oi_retreat_thresholds:
                    completed += 1
                    if completed > max_trials:
                        data_warnings.append(f"trial_grid_truncated_at_{max_trials}")
                        break
                    predicate = _trial_predicate(
                        funding_threshold=funding_threshold,
                        oi_threshold=oi_threshold,
                        failed_breakout_window=failed_breakout_window,
                        oi_retreat_threshold=oi_retreat_threshold,
                    )
                    event_count = sum(1 for item in features if predicate(item))
                    returns = _simulate_returns(
                        sorted_candles,
                        features,
                        horizon_bars=horizon_bars,
                        fee_rate=fee_rate,
                        predicate=predicate,
                    )
                    stats = _stats_from_returns(returns)
                    trials.append(
                        EventDefinitionSensitivityTrial(
                            trial_id=(
                                f"trial_f{_fmt_threshold(funding_threshold)}"
                                f"_oi{_fmt_threshold(oi_threshold)}"
                                f"_fb{failed_breakout_window}"
                                f"_ret{_fmt_threshold(oi_retreat_threshold * 1000)}"
                            ),
                            funding_percentile_threshold=funding_threshold,
                            oi_percentile_threshold=oi_threshold,
                            failed_breakout_window=failed_breakout_window,
                            oi_retreat_threshold=oi_retreat_threshold,
                            event_count=event_count,
                            trade_count=len(returns),
                            average_return=round(stats["average_return"], 6),
                            total_return=round(stats["total_return"], 6),
                            profit_factor=round(stats["profit_factor"], 6),
                            sharpe=stats["sharpe"],
                            max_drawdown=round(stats["max_drawdown"], 6),
                            beats_cash=stats["total_return"] > 0,
                            beats_funding_only=stats["total_return"] > funding_only_stats["total_return"],
                        )
                    )
                else:
                    continue
                break
            else:
                continue
            break
        else:
            continue
        break

    best_trial = _select_best_trial(trials, min_trade_count)
    robust_trial_count = sum(
        1
        for trial in trials
        if trial.trade_count >= min_trade_count
        and trial.total_return > 0
        and trial.profit_factor > 1
        and trial.beats_funding_only
    )
    findings = _findings(
        trials=trials,
        best_trial=best_trial,
        robust_trial_count=robust_trial_count,
        min_trade_count=min_trade_count,
        funding_only_trade_count=len(funding_only_returns),
        data_warnings=data_warnings,
    )
    return EventDefinitionSensitivityReport(
        report_id=f"event_definition_{_safe_symbol(symbol)}_{uuid4().hex[:8]}",
        task_id=None if task is None else task.task_id,
        thesis_id=None if task is None else task.thesis_id,
        signal_id=None if task is None else task.signal_id,
        strategy_id=None if task is None else task.strategy_id,
        strategy_family=StrategyFamily.FUNDING_CROWDING_FADE.value,
        symbol=symbol,
        timeframe=timeframe,
        horizon_hours=horizon_hours,
        search_budget_trials=search_budget,
        completed_trials=len(trials),
        funding_only_total_return=round(funding_only_stats["total_return"], 6),
        funding_only_profit_factor=round(funding_only_stats["profit_factor"], 6),
        funding_only_trade_count=len(funding_only_returns),
        best_trial=best_trial,
        robust_trial_count=robust_trial_count,
        min_trade_count=min_trade_count,
        trials=trials,
        data_warnings=list(dict.fromkeys(data_warnings)),
        findings=findings,
    )


def build_failed_breakout_universe_report(
    *,
    task: ResearchTask | None,
    reports: list[FailedBreakoutSensitivityReport],
    skipped_cells: list[str] | None = None,
    min_market_confirmations: int = 2,
    min_trade_count: int = 50,
) -> FailedBreakoutUniverseReport:
    """Aggregate Failed Breakout event-definition reports across markets and timeframes."""
    skipped_cells = skipped_cells or []
    cells = [_failed_breakout_cell_from_report(report) for report in reports]
    robust_counts: dict[str, int] = {}
    best_counts: dict[str, int] = {}
    for report in reports:
        if report.best_trial is not None:
            best_counts[report.best_trial.trial_id] = best_counts.get(report.best_trial.trial_id, 0) + 1
        for trial in report.trials:
            if (
                trial.trade_count >= min_trade_count
                and trial.total_return > 0
                and trial.profit_factor > 1
                and trial.beats_simple_failed_breakout
            ):
                robust_counts[trial.trial_id] = robust_counts.get(trial.trial_id, 0) + 1
    robust_trial_ids = sorted(
        [trial_id for trial_id, count in robust_counts.items() if count >= min_market_confirmations]
    )
    symbols = sorted({report.symbol for report in reports})
    timeframes = sorted({report.timeframe for report in reports})
    findings = _failed_breakout_universe_findings(
        reports=reports,
        cells=cells,
        skipped_cells=skipped_cells,
        robust_trial_ids=robust_trial_ids,
        robust_counts=robust_counts,
        best_counts=best_counts,
        min_market_confirmations=min_market_confirmations,
    )
    return FailedBreakoutUniverseReport(
        report_id=f"failed_breakout_universe_{uuid4().hex[:8]}",
        task_id=None if task is None else task.task_id,
        thesis_id=None if task is None else task.thesis_id,
        signal_id=None if task is None else task.signal_id,
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        symbols=symbols,
        timeframes=timeframes,
        completed_cells=len(reports),
        skipped_cells=skipped_cells,
        min_market_confirmations=min_market_confirmations,
        robust_trial_ids=robust_trial_ids,
        best_trial_frequency=dict(sorted(best_counts.items(), key=lambda item: (-item[1], item[0]))),
        cells=cells,
        child_report_ids=[report.report_id for report in reports],
        findings=findings,
    )


def run_failed_breakout_event_definition_sensitivity(
    *,
    task: ResearchTask | None,
    candles: list[OhlcvCandle],
    symbol: str,
    timeframe: str,
    sides: tuple[str, ...] = ("short",),
    level_lookback_bars: tuple[int, ...] = (48, 96, 192),
    breakout_depth_bps: tuple[float, ...] = (10, 25, 50),
    acceptance_window_bars: tuple[int, ...] = (3, 6, 10),
    volume_zscore_thresholds: tuple[float, ...] = (0, 1, 1.5, 2),
    horizon_hours: int = 2,
    min_trade_count: int = 50,
    fee_rate: float = 0.001,
    max_trials: int = 200,
) -> FailedBreakoutSensitivityReport:
    """Run a bounded OHLCV-only event-definition grid for Failed Breakout Punishment."""
    sorted_candles = sorted(candles, key=lambda item: item.open_time)
    data_warnings: list[str] = []
    normalized_sides = tuple(dict.fromkeys(side.lower() for side in sides if side.lower() in {"short", "long"}))
    if not normalized_sides:
        normalized_sides = ("short",)
        data_warnings.append("invalid_side_defaulted_to_short")
    if len(sorted_candles) < max(level_lookback_bars) + max(acceptance_window_bars) + 30:
        data_warnings.append("limited_ohlcv_history_for_failed_breakout_scan")

    horizon_bars = _bars_for_duration(timeframe, hours=horizon_hours)
    baseline_returns = _simulate_failed_breakout_returns(
        sorted_candles,
        sides=normalized_sides,
        level_lookback_bars=96,
        breakout_depth_bps=10,
        acceptance_window_bars=6,
        volume_zscore_threshold=0,
        horizon_bars=horizon_bars,
        fee_rate=fee_rate,
    )
    baseline_stats = _stats_from_returns(baseline_returns)

    search_budget = (
        len(normalized_sides)
        * len(level_lookback_bars)
        * len(breakout_depth_bps)
        * len(acceptance_window_bars)
        * len(volume_zscore_thresholds)
    )
    completed = 0
    trials: list[FailedBreakoutSensitivityTrial] = []
    for side in normalized_sides:
        for lookback in level_lookback_bars:
            for depth_bps in breakout_depth_bps:
                for acceptance_window in acceptance_window_bars:
                    for volume_threshold in volume_zscore_thresholds:
                        completed += 1
                        if completed > max_trials:
                            data_warnings.append(f"trial_grid_truncated_at_{max_trials}")
                            break
                        events = _failed_breakout_event_indices(
                            sorted_candles,
                            side=side,
                            level_lookback_bars=lookback,
                            breakout_depth_bps=depth_bps,
                            acceptance_window_bars=acceptance_window,
                            volume_zscore_threshold=volume_threshold,
                        )
                        returns = _simulate_failed_breakout_returns(
                            sorted_candles,
                            sides=(side,),
                            level_lookback_bars=lookback,
                            breakout_depth_bps=depth_bps,
                            acceptance_window_bars=acceptance_window,
                            volume_zscore_threshold=volume_threshold,
                            horizon_bars=horizon_bars,
                            fee_rate=fee_rate,
                        )
                        stats = _stats_from_returns(returns)
                        trials.append(
                            FailedBreakoutSensitivityTrial(
                                trial_id=(
                                    f"trial_{side}"
                                    f"_lb{lookback}"
                                    f"_d{_fmt_threshold(depth_bps)}"
                                    f"_aw{acceptance_window}"
                                    f"_vz{_fmt_threshold(volume_threshold)}"
                                ),
                                side=side,
                                level_lookback_bars=lookback,
                                breakout_depth_bps=depth_bps,
                                acceptance_window_bars=acceptance_window,
                                volume_zscore_threshold=volume_threshold,
                                event_count=len(events),
                                trade_count=len(returns),
                                average_return=round(stats["average_return"], 6),
                                total_return=round(stats["total_return"], 6),
                                profit_factor=round(stats["profit_factor"], 6),
                                sharpe=stats["sharpe"],
                                max_drawdown=round(stats["max_drawdown"], 6),
                                beats_cash=stats["total_return"] > 0,
                                beats_simple_failed_breakout=stats["total_return"] > baseline_stats["total_return"],
                            )
                        )
                    else:
                        continue
                    break
                else:
                    continue
                break
            else:
                continue
            break
        else:
            continue
        break

    best_trial = _select_best_failed_breakout_trial(trials, min_trade_count)
    robust_trial_count = sum(
        1
        for trial in trials
        if trial.trade_count >= min_trade_count
        and trial.total_return > 0
        and trial.profit_factor > 1
        and trial.beats_simple_failed_breakout
    )
    findings = _failed_breakout_findings(
        trials=trials,
        best_trial=best_trial,
        robust_trial_count=robust_trial_count,
        min_trade_count=min_trade_count,
        baseline_trade_count=len(baseline_returns),
        data_warnings=data_warnings,
    )
    return FailedBreakoutSensitivityReport(
        report_id=f"failed_breakout_{_safe_symbol(symbol)}_{uuid4().hex[:8]}",
        task_id=None if task is None else task.task_id,
        thesis_id=None if task is None else task.thesis_id,
        signal_id=None if task is None else task.signal_id,
        strategy_id=None if task is None else task.strategy_id,
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        symbol=symbol,
        timeframe=timeframe,
        horizon_hours=horizon_hours,
        search_budget_trials=search_budget,
        completed_trials=len(trials),
        simple_failed_breakout_total_return=round(baseline_stats["total_return"], 6),
        simple_failed_breakout_profit_factor=round(baseline_stats["profit_factor"], 6),
        simple_failed_breakout_trade_count=len(baseline_returns),
        best_trial=best_trial,
        robust_trial_count=robust_trial_count,
        min_trade_count=min_trade_count,
        trials=trials,
        data_warnings=list(dict.fromkeys(data_warnings)),
        findings=findings,
    )


def _precompute_features(
    candles: list[OhlcvCandle],
    funding_rates: list[FundingRatePoint],
    open_interest_points: list[OpenInterestPoint],
    failed_breakout_windows: tuple[int, ...],
    timeframe: str,
) -> list[dict[str, float | bool]]:
    features: list[dict[str, float | bool]] = []
    funding_index = 0
    oi_index = 0
    funding_window: list[float] = []
    oi_window: list[float] = []
    oi_by_index: list[float | None] = []
    bars_24h = _bars_for_duration(timeframe, hours=24)
    max_failed_window = max(failed_breakout_windows)
    for index, candle in enumerate(candles):
        candle_timestamp = _datetime_seconds(candle.open_time)
        while funding_index < len(funding_rates) and _datetime_seconds(funding_rates[funding_index].funding_time) <= candle_timestamp:
            funding_window.append(funding_rates[funding_index].funding_rate)
            funding_index += 1
        if open_interest_points:
            while oi_index < len(open_interest_points) and _datetime_seconds(open_interest_points[oi_index].timestamp) <= candle_timestamp:
                oi_window.append(open_interest_points[oi_index].open_interest)
                oi_index += 1
        latest_oi = oi_window[-1] if oi_window else None
        oi_by_index.append(latest_oi)
        if oi_window:
            oi_percentile = _latest_percentile(oi_window[-90:], oi_window[-1])
        else:
            volume_window = [item.volume for item in candles[max(0, index - 90) : index + 1]]
            oi_percentile = _latest_percentile(volume_window, candle.volume)
        item: dict[str, float | bool] = {
            "funding_percentile": _latest_percentile(funding_window[-90:], funding_window[-1]) if funding_window else 50.0,
            "oi_percentile": oi_percentile,
            "price_change_24h": candle.close / candles[max(0, index - bars_24h)].close - 1,
        }
        for window in failed_breakout_windows:
            item[f"failed_breakout_{window}"] = _failed_breakout(candles, index, window)
            item[f"oi_retreat_{window}"] = _oi_retreat(oi_by_index, index, window)
        if max_failed_window not in failed_breakout_windows:
            item[f"failed_breakout_{max_failed_window}"] = _failed_breakout(candles, index, max_failed_window)
        features.append(item)
    return features


def _cell_from_report(report: EventDefinitionSensitivityReport) -> EventDefinitionUniverseCell:
    best = report.best_trial
    return EventDefinitionUniverseCell(
        report_id=report.report_id,
        symbol=report.symbol,
        timeframe=report.timeframe,
        completed_trials=report.completed_trials,
        robust_trial_count=report.robust_trial_count,
        funding_only_total_return=report.funding_only_total_return,
        funding_only_trade_count=report.funding_only_trade_count,
        best_trial_id=None if best is None else best.trial_id,
        best_trial_trade_count=0 if best is None else best.trade_count,
        best_trial_total_return=0 if best is None else best.total_return,
        best_trial_profit_factor=0 if best is None else best.profit_factor,
        best_trial_sharpe=None if best is None else best.sharpe,
        data_warnings=report.data_warnings,
    )


def _universe_findings(
    *,
    reports: list[EventDefinitionSensitivityReport],
    cells: list[EventDefinitionUniverseCell],
    skipped_cells: list[str],
    robust_trial_ids: list[str],
    robust_counts: dict[str, int],
    best_counts: dict[str, int],
    min_market_confirmations: int,
) -> list[str]:
    findings = [
        f"Completed event-definition universe scan over {len(reports)} market/timeframe cell(s).",
    ]
    if skipped_cells:
        findings.append(f"Skipped {len(skipped_cells)} cell(s): {', '.join(skipped_cells)}.")
    if not reports:
        findings.append("No usable market/timeframe cells were available.")
        return findings
    positive_best = sum(1 for cell in cells if cell.best_trial_total_return > 0)
    sufficient_best = sum(1 for cell in cells if cell.best_trial_trade_count >= 20)
    findings.append(
        f"{positive_best}/{len(cells)} cell(s) had a positive best trial; "
        f"{sufficient_best}/{len(cells)} best trials met the default 20-trade sample floor."
    )
    if robust_trial_ids:
        counts = ", ".join(f"{trial_id}:{robust_counts[trial_id]}" for trial_id in robust_trial_ids)
        findings.append(
            f"Cross-market robust trial ids meeting {min_market_confirmations} confirmation(s): {counts}."
        )
    else:
        findings.append(
            f"No trial id met cross-market robust confirmation threshold={min_market_confirmations}; "
            "treat isolated best cells as research leads, not alpha evidence."
        )
    if sufficient_best == 0 and not robust_trial_ids:
        findings.append(
            "Scope control: pause Funding Crowding Fade optimization and do not spend more resources "
            "inventing proxy data for this template; switch the next Harness cycle toward naturally "
            "higher-frequency strategy families."
        )
    if best_counts:
        top_best = next(iter(dict(sorted(best_counts.items(), key=lambda item: (-item[1], item[0]))).items()))
        findings.append(f"Most frequent best trial was {top_best[0]} in {top_best[1]} cell(s).")
    warnings = sorted({warning for report in reports for warning in report.data_warnings})
    if warnings:
        findings.append(f"Data warnings observed: {', '.join(warnings)}.")
    return findings


def _trial_predicate(
    *,
    funding_threshold: float,
    oi_threshold: float,
    failed_breakout_window: int,
    oi_retreat_threshold: float,
):
    def predicate(features: dict[str, float | bool]) -> bool:
        if float(features["funding_percentile"]) < funding_threshold:
            return False
        if float(features["oi_percentile"]) < oi_threshold:
            return False
        if float(features["price_change_24h"]) <= 0:
            return False
        if not bool(features[f"failed_breakout_{failed_breakout_window}"]):
            return False
        if oi_retreat_threshold > 0 and float(features[f"oi_retreat_{failed_breakout_window}"]) < oi_retreat_threshold:
            return False
        return True

    return predicate


def _simulate_returns(
    candles: list[OhlcvCandle],
    features: list[dict[str, float | bool]],
    *,
    horizon_bars: int,
    fee_rate: float,
    predicate,
) -> list[float]:
    returns: list[float] = []
    index = max(64, horizon_bars)
    while index + horizon_bars < len(candles):
        if predicate(features[index]):
            entry = candles[index].close
            exit_ = candles[index + horizon_bars].close
            returns.append(entry / exit_ - 1 - fee_rate)
            index += horizon_bars
        else:
            index += 1
    return returns


def _failed_breakout(candles: list[OhlcvCandle], index: int, window: int, lookback: int = 48) -> bool:
    if index < lookback + window:
        return False
    range_high = max(item.high for item in candles[index - lookback - window + 1 : index - window + 1])
    recent_high = max(item.high for item in candles[index - window + 1 : index + 1])
    return recent_high > range_high and candles[index].close < range_high


def _oi_retreat(oi_by_index: list[float | None], index: int, window: int) -> float:
    if index < window:
        return 0.0
    current = oi_by_index[index]
    previous = oi_by_index[index - window]
    if current is None or previous is None or previous <= 0:
        return 0.0
    return max(0.0, previous / current - 1)


def _stats_from_returns(returns: list[float]) -> dict[str, float | None]:
    if not returns:
        return {
            "average_return": 0.0,
            "total_return": 0.0,
            "profit_factor": 0.0,
            "sharpe": None,
            "max_drawdown": 0.0,
        }
    gross_profit = sum(item for item in returns if item > 0)
    gross_loss = abs(sum(item for item in returns if item < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
    return {
        "average_return": mean(returns),
        "total_return": _compound_return(returns),
        "profit_factor": profit_factor,
        "sharpe": _sharpe(returns),
        "max_drawdown": _max_drawdown(returns),
    }


def _select_best_trial(
    trials: list[EventDefinitionSensitivityTrial],
    min_trade_count: int,
) -> EventDefinitionSensitivityTrial | None:
    candidates = [trial for trial in trials if trial.trade_count >= min_trade_count]
    if not candidates:
        candidates = [trial for trial in trials if trial.trade_count > 0]
    return max(candidates, key=lambda item: (item.beats_funding_only, item.total_return, item.profit_factor), default=None)


def _findings(
    *,
    trials: list[EventDefinitionSensitivityTrial],
    best_trial: EventDefinitionSensitivityTrial | None,
    robust_trial_count: int,
    min_trade_count: int,
    funding_only_trade_count: int,
    data_warnings: list[str],
) -> list[str]:
    findings: list[str] = [
        f"Completed {len(trials)} bounded event-definition trial(s).",
        f"Funding-only comparison produced {funding_only_trade_count} non-overlapping trade(s).",
    ]
    if data_warnings:
        findings.append(f"Data warnings: {', '.join(sorted(set(data_warnings)))}.")
    if best_trial is None:
        findings.append("No usable event-definition trial was produced.")
        return findings
    findings.append(
        "Best trial "
        f"{best_trial.trial_id}: trades={best_trial.trade_count}, "
        f"return={best_trial.total_return:.4f}, PF={best_trial.profit_factor:.2f}, "
        f"Sharpe={best_trial.sharpe}."
    )
    if best_trial.trade_count < min_trade_count:
        findings.append(
            f"Best trial has only {best_trial.trade_count} trade(s), below min_trade_count={min_trade_count}; "
            "treat the result as event-frequency evidence, not alpha evidence."
        )
    if robust_trial_count == 0:
        findings.append("No parameter neighborhood beat cash and funding-only with sufficient sample count.")
    elif robust_trial_count < 3:
        findings.append("Only a very small robust region was found; overfitting risk remains high.")
    else:
        findings.append(f"{robust_trial_count} trials passed the bounded robustness screen.")
    return findings


def _failed_breakout_cell_from_report(report: FailedBreakoutSensitivityReport) -> FailedBreakoutUniverseCell:
    best = report.best_trial
    return FailedBreakoutUniverseCell(
        report_id=report.report_id,
        symbol=report.symbol,
        timeframe=report.timeframe,
        completed_trials=report.completed_trials,
        robust_trial_count=report.robust_trial_count,
        simple_failed_breakout_total_return=report.simple_failed_breakout_total_return,
        simple_failed_breakout_trade_count=report.simple_failed_breakout_trade_count,
        best_trial_id=None if best is None else best.trial_id,
        best_trial_trade_count=0 if best is None else best.trade_count,
        best_trial_total_return=0 if best is None else best.total_return,
        best_trial_profit_factor=0 if best is None else best.profit_factor,
        best_trial_sharpe=None if best is None else best.sharpe,
        data_warnings=report.data_warnings,
    )


def _failed_breakout_universe_findings(
    *,
    reports: list[FailedBreakoutSensitivityReport],
    cells: list[FailedBreakoutUniverseCell],
    skipped_cells: list[str],
    robust_trial_ids: list[str],
    robust_counts: dict[str, int],
    best_counts: dict[str, int],
    min_market_confirmations: int,
) -> list[str]:
    findings = [
        f"Completed Failed Breakout universe scan over {len(reports)} market/timeframe cell(s).",
    ]
    if skipped_cells:
        findings.append(f"Skipped {len(skipped_cells)} cell(s): {', '.join(skipped_cells)}.")
    if not reports:
        findings.append("No usable OHLCV cell was available for Failed Breakout Punishment.")
        return findings
    positive_best = sum(1 for cell in cells if cell.best_trial_total_return > 0)
    sufficient_best = sum(1 for cell in cells if cell.best_trial_trade_count >= 50)
    findings.append(
        f"{positive_best}/{len(cells)} cell(s) had a positive best trial; "
        f"{sufficient_best}/{len(cells)} best trials met the default 50-trade sample floor."
    )
    if robust_trial_ids:
        counts = ", ".join(f"{trial_id}:{robust_counts[trial_id]}" for trial_id in robust_trial_ids)
        findings.append(
            f"Cross-market robust trial ids meeting {min_market_confirmations} confirmation(s): {counts}."
        )
    else:
        findings.append(
            f"No Failed Breakout trial id met cross-market robust confirmation threshold="
            f"{min_market_confirmations}; use the best cells as event-definition leads only."
        )
    if best_counts:
        top_best = next(iter(dict(sorted(best_counts.items(), key=lambda item: (-item[1], item[0]))).items()))
        findings.append(f"Most frequent best trial was {top_best[0]} in {top_best[1]} cell(s).")
    warnings = sorted({warning for report in reports for warning in report.data_warnings})
    if warnings:
        findings.append(f"Data warnings observed: {', '.join(warnings)}.")
    return findings


def _simulate_failed_breakout_returns(
    candles: list[OhlcvCandle],
    *,
    sides: tuple[str, ...],
    level_lookback_bars: int,
    breakout_depth_bps: float,
    acceptance_window_bars: int,
    volume_zscore_threshold: float,
    horizon_bars: int,
    fee_rate: float,
) -> list[float]:
    events: list[tuple[int, str]] = []
    for side in sides:
        events.extend(
            (index, side)
            for index in _failed_breakout_event_indices(
                candles,
                side=side,
                level_lookback_bars=level_lookback_bars,
                breakout_depth_bps=breakout_depth_bps,
                acceptance_window_bars=acceptance_window_bars,
                volume_zscore_threshold=volume_zscore_threshold,
            )
        )
    events.sort()
    returns: list[float] = []
    next_available_index = 0
    for index, side in events:
        if index < next_available_index or index + horizon_bars >= len(candles):
            continue
        entry = candles[index].close
        exit_ = candles[index + horizon_bars].close
        if entry <= 0 or exit_ <= 0:
            continue
        if side == "short":
            returns.append(entry / exit_ - 1 - fee_rate)
        else:
            returns.append(exit_ / entry - 1 - fee_rate)
        next_available_index = index + horizon_bars
    return returns


def _failed_breakout_event_indices(
    candles: list[OhlcvCandle],
    *,
    side: str,
    level_lookback_bars: int,
    breakout_depth_bps: float,
    acceptance_window_bars: int,
    volume_zscore_threshold: float,
) -> list[int]:
    indices: list[int] = []
    start = level_lookback_bars + acceptance_window_bars
    for index in range(start, len(candles)):
        level_window_start = index - acceptance_window_bars - level_lookback_bars + 1
        level_window_end = index - acceptance_window_bars + 1
        level_window = candles[level_window_start:level_window_end]
        recent_window = candles[index - acceptance_window_bars + 1 : index + 1]
        if len(level_window) < level_lookback_bars or len(recent_window) < acceptance_window_bars:
            continue
        if volume_zscore_threshold > 0 and _volume_zscore(candles, index) < volume_zscore_threshold:
            continue
        if side == "short":
            level = max(item.high for item in level_window)
            breakout_price = level * (1 + breakout_depth_bps / 10000)
            broke_out = max(item.high for item in recent_window) >= breakout_price
            returned_inside = candles[index].close < level
            if broke_out and returned_inside:
                indices.append(index)
        else:
            level = min(item.low for item in level_window)
            breakdown_price = level * (1 - breakout_depth_bps / 10000)
            broke_out = min(item.low for item in recent_window) <= breakdown_price
            returned_inside = candles[index].close > level
            if broke_out and returned_inside:
                indices.append(index)
    return indices


def _volume_zscore(candles: list[OhlcvCandle], index: int, lookback: int = 48) -> float:
    if index < 2:
        return 0.0
    window = [item.volume for item in candles[max(0, index - lookback) : index]]
    if len(window) < 2:
        return 0.0
    stdev = pstdev(window)
    if stdev == 0:
        return 0.0
    return (candles[index].volume - mean(window)) / stdev


def _select_best_failed_breakout_trial(
    trials: list[FailedBreakoutSensitivityTrial],
    min_trade_count: int,
) -> FailedBreakoutSensitivityTrial | None:
    candidates = [trial for trial in trials if trial.trade_count >= min_trade_count]
    if not candidates:
        candidates = [trial for trial in trials if trial.trade_count > 0]
    return max(
        candidates,
        key=lambda item: (item.beats_simple_failed_breakout, item.total_return, item.profit_factor),
        default=None,
    )


def _failed_breakout_findings(
    *,
    trials: list[FailedBreakoutSensitivityTrial],
    best_trial: FailedBreakoutSensitivityTrial | None,
    robust_trial_count: int,
    min_trade_count: int,
    baseline_trade_count: int,
    data_warnings: list[str],
) -> list[str]:
    findings: list[str] = [
        f"Completed {len(trials)} bounded Failed Breakout event-definition trial(s).",
        f"Simple failed-breakout baseline produced {baseline_trade_count} non-overlapping trade(s).",
    ]
    if data_warnings:
        findings.append(f"Data warnings: {', '.join(sorted(set(data_warnings)))}.")
    if best_trial is None:
        findings.append("No usable Failed Breakout trial was produced.")
        return findings
    findings.append(
        "Best trial "
        f"{best_trial.trial_id}: trades={best_trial.trade_count}, "
        f"return={best_trial.total_return:.4f}, PF={best_trial.profit_factor:.2f}, "
        f"Sharpe={best_trial.sharpe}."
    )
    if best_trial.trade_count < min_trade_count:
        findings.append(
            f"Best trial has only {best_trial.trade_count} trade(s), below min_trade_count={min_trade_count}; "
            "do not move this template into optimizer yet."
        )
    if robust_trial_count == 0:
        findings.append("No parameter neighborhood beat cash and simple failed-breakout baseline with sufficient sample count.")
    elif robust_trial_count < 3:
        findings.append("Only a narrow robust region was found; keep the scope limited before optimizer work.")
    else:
        findings.append(f"{robust_trial_count} trials passed the bounded robustness screen.")
    return findings


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


def _fmt_threshold(value: float) -> str:
    return str(value).replace(".", "p").replace("-", "m")


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_").lower()
