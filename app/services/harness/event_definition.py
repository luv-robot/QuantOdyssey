from __future__ import annotations

import re
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
    level_sources: tuple[str, ...] = ("rolling_extreme",),
    level_lookback_bars: tuple[int, ...] = (48, 96, 192),
    level_quality_thresholds: tuple[float, ...] = (0,),
    breakout_depth_bps: tuple[float, ...] = (10, 25, 50),
    acceptance_window_bars: tuple[int, ...] = (3, 6, 10),
    acceptance_failure_thresholds: tuple[float, ...] = (0,),
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
    normalized_sources = tuple(
        dict.fromkeys(source.lower() for source in level_sources if source.lower() in {"rolling_extreme", "swing_extreme"})
    )
    if not normalized_sources:
        normalized_sources = ("rolling_extreme",)
        data_warnings.append("invalid_level_source_defaulted_to_rolling_extreme")
    if len(sorted_candles) < max(level_lookback_bars) + max(acceptance_window_bars) + 30:
        data_warnings.append("limited_ohlcv_history_for_failed_breakout_scan")

    horizon_bars = _bars_for_duration(timeframe, hours=horizon_hours)
    baseline_returns = _simulate_failed_breakout_returns(
        sorted_candles,
        sides=normalized_sides,
        level_source="rolling_extreme",
        level_lookback_bars=96,
        level_quality_threshold=0,
        breakout_depth_bps=10,
        acceptance_window_bars=6,
        acceptance_failure_threshold=0,
        volume_zscore_threshold=0,
        horizon_bars=horizon_bars,
        fee_rate=fee_rate,
    )
    baseline_stats = _stats_from_returns(baseline_returns)

    search_budget = (
        len(normalized_sides)
        * len(normalized_sources)
        * len(level_lookback_bars)
        * len(level_quality_thresholds)
        * len(breakout_depth_bps)
        * len(acceptance_window_bars)
        * len(acceptance_failure_thresholds)
        * len(volume_zscore_thresholds)
    )
    completed = 0
    trials: list[FailedBreakoutSensitivityTrial] = []
    base_scan_cache: dict[tuple[str, str, int, int], list[dict]] = {}
    for side in normalized_sides:
        for level_source in normalized_sources:
            for lookback in level_lookback_bars:
                for level_quality_threshold in level_quality_thresholds:
                    for depth_bps in breakout_depth_bps:
                        for acceptance_window in acceptance_window_bars:
                            for acceptance_failure_threshold in acceptance_failure_thresholds:
                                for volume_threshold in volume_zscore_thresholds:
                                    completed += 1
                                    if completed > max_trials:
                                        data_warnings.append(f"trial_grid_truncated_at_{max_trials}")
                                        break
                                    cache_key = (side, level_source, lookback, acceptance_window)
                                    if cache_key not in base_scan_cache:
                                        base_scan_cache[cache_key] = _failed_breakout_base_scan(
                                            sorted_candles,
                                            side=side,
                                            level_source=level_source,
                                            level_lookback_bars=lookback,
                                            acceptance_window_bars=acceptance_window,
                                        )
                                    event_scan = _failed_breakout_event_scan_from_base(
                                        base_scan_cache[cache_key],
                                        level_quality_threshold=level_quality_threshold,
                                        breakout_depth_bps=depth_bps,
                                        acceptance_failure_threshold=acceptance_failure_threshold,
                                        volume_zscore_threshold=volume_threshold,
                                    )
                                    returns = _returns_from_failed_breakout_events(
                                        sorted_candles,
                                        event_scan["events"],
                                        side=side,
                                        horizon_bars=horizon_bars,
                                        fee_rate=fee_rate,
                                    )
                                    stats = _stats_from_returns(returns)
                                    trials.append(
                                        FailedBreakoutSensitivityTrial(
                                            trial_id=(
                                                f"trial_{side}"
                                                f"_{level_source}"
                                                f"_lb{lookback}"
                                                f"_lq{_fmt_threshold(level_quality_threshold)}"
                                                f"_d{_fmt_threshold(depth_bps)}"
                                                f"_aw{acceptance_window}"
                                                f"_af{_fmt_threshold(acceptance_failure_threshold)}"
                                                f"_vz{_fmt_threshold(volume_threshold)}"
                                            ),
                                            side=side,
                                            level_source=level_source,
                                            level_lookback_bars=lookback,
                                            level_quality_threshold=level_quality_threshold,
                                            breakout_depth_bps=depth_bps,
                                            acceptance_window_bars=acceptance_window,
                                            acceptance_failure_threshold=acceptance_failure_threshold,
                                            volume_zscore_threshold=volume_threshold,
                                            event_count=len(event_scan["events"]),
                                            trade_count=len(returns),
                                            average_return=round(stats["average_return"], 6),
                                            total_return=round(stats["total_return"], 6),
                                            profit_factor=round(stats["profit_factor"], 6),
                                            sharpe=stats["sharpe"],
                                            max_drawdown=round(stats["max_drawdown"], 6),
                                            beats_cash=stats["total_return"] > 0,
                                            beats_simple_failed_breakout=stats["total_return"] > baseline_stats["total_return"],
                                            event_funnel=event_scan["funnel"],
                                            level_source_counts=event_scan["level_source_counts"],
                                            average_level_quality_score=round(event_scan["average_level_quality_score"], 3),
                                            average_acceptance_failure_score=round(
                                                event_scan["average_acceptance_failure_score"], 3
                                            ),
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
        event_funnel={} if best_trial is None else best_trial.event_funnel,
        level_source_counts={} if best_trial is None else best_trial.level_source_counts,
        data_warnings=list(dict.fromkeys(data_warnings)),
        findings=findings,
    )


def parse_failed_breakout_trial_id(trial_id: str) -> dict[str, str | int | float]:
    """Decode a Failed Breakout trial id into the event-definition parameters it represents."""
    pattern = re.compile(
        r"^trial_(?P<side>short|long)_(?P<level_source>.+)"
        r"_lb(?P<lookback>\d+)"
        r"_lq(?P<quality>[0-9mp]+)"
        r"_d(?P<depth>[0-9mp]+)"
        r"_aw(?P<acceptance_window>\d+)"
        r"_af(?P<acceptance_failure>[0-9mp]+)"
        r"_vz(?P<volume>[0-9mp]+)$"
    )
    match = pattern.match(trial_id)
    if match is None:
        raise ValueError(f"Unsupported Failed Breakout trial id: {trial_id}")
    return {
        "side": match.group("side"),
        "level_source": match.group("level_source"),
        "level_lookback_bars": int(match.group("lookback")),
        "level_quality_threshold": _parse_threshold_token(match.group("quality")),
        "breakout_depth_bps": _parse_threshold_token(match.group("depth")),
        "acceptance_window_bars": int(match.group("acceptance_window")),
        "acceptance_failure_threshold": _parse_threshold_token(match.group("acceptance_failure")),
        "volume_zscore_threshold": _parse_threshold_token(match.group("volume")),
    }


def simulate_failed_breakout_trial_returns(
    candles: list[OhlcvCandle],
    *,
    timeframe: str,
    trial_id: str,
    horizon_hours: int = 2,
    fee_rate: float = 0.001,
) -> list[float]:
    """Replay one encoded Failed Breakout trial id and return its non-overlapping trade returns."""
    params = parse_failed_breakout_trial_id(trial_id)
    horizon_bars = _bars_for_duration(timeframe, hours=horizon_hours)
    return _simulate_failed_breakout_returns(
        sorted(candles, key=lambda item: item.open_time),
        sides=(str(params["side"]),),
        level_source=str(params["level_source"]),
        level_lookback_bars=int(params["level_lookback_bars"]),
        level_quality_threshold=float(params["level_quality_threshold"]),
        breakout_depth_bps=float(params["breakout_depth_bps"]),
        acceptance_window_bars=int(params["acceptance_window_bars"]),
        acceptance_failure_threshold=float(params["acceptance_failure_threshold"]),
        volume_zscore_threshold=float(params["volume_zscore_threshold"]),
        horizon_bars=horizon_bars,
        fee_rate=fee_rate,
    )


def scan_failed_breakout_trial_events(
    candles: list[OhlcvCandle],
    *,
    timeframe: str,
    trial_id: str,
    horizon_hours: int = 2,
    fee_rate: float = 0.001,
) -> list[dict]:
    """Replay one Failed Breakout trial id and return event metadata plus fixed-horizon return."""
    params = parse_failed_breakout_trial_id(trial_id)
    sorted_candles = sorted(candles, key=lambda item: item.open_time)
    horizon_bars = _bars_for_duration(timeframe, hours=horizon_hours)
    event_scan = _failed_breakout_event_scan(
        sorted_candles,
        side=str(params["side"]),
        level_source=str(params["level_source"]),
        level_lookback_bars=int(params["level_lookback_bars"]),
        level_quality_threshold=float(params["level_quality_threshold"]),
        breakout_depth_bps=float(params["breakout_depth_bps"]),
        acceptance_window_bars=int(params["acceptance_window_bars"]),
        acceptance_failure_threshold=float(params["acceptance_failure_threshold"]),
        volume_zscore_threshold=float(params["volume_zscore_threshold"]),
    )
    events: list[dict] = []
    next_available_index = 0
    for event in event_scan["events"]:
        index = int(event["index"])
        if index < next_available_index or index + horizon_bars >= len(sorted_candles):
            continue
        entry = sorted_candles[index].close
        exit_ = sorted_candles[index + horizon_bars].close
        if entry <= 0 or exit_ <= 0:
            continue
        side = str(params["side"])
        trade_return = entry / exit_ - 1 - fee_rate if side == "short" else exit_ / entry - 1 - fee_rate
        events.append(
            {
                **event,
                "index": index,
                "event_time": sorted_candles[index].open_time,
                "side": side,
                "trial_id": trial_id,
                "trade_return": trade_return,
                "acceptance_window_bars": int(params["acceptance_window_bars"]),
            }
        )
        next_available_index = index + horizon_bars
    return events


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
    level_source: str,
    level_lookback_bars: int,
    level_quality_threshold: float,
    breakout_depth_bps: float,
    acceptance_window_bars: int,
    acceptance_failure_threshold: float,
    volume_zscore_threshold: float,
    horizon_bars: int,
    fee_rate: float,
) -> list[float]:
    events: list[tuple[int, str]] = []
    for side in sides:
        event_scan = _failed_breakout_event_scan(
            candles,
            side=side,
            level_source=level_source,
            level_lookback_bars=level_lookback_bars,
            level_quality_threshold=level_quality_threshold,
            breakout_depth_bps=breakout_depth_bps,
            acceptance_window_bars=acceptance_window_bars,
            acceptance_failure_threshold=acceptance_failure_threshold,
            volume_zscore_threshold=volume_zscore_threshold,
        )
        events.extend(
            (int(event["index"]), side)
            for event in event_scan["events"]
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


def _returns_from_failed_breakout_events(
    candles: list[OhlcvCandle],
    events: list[dict],
    *,
    side: str,
    horizon_bars: int,
    fee_rate: float,
) -> list[float]:
    returns: list[float] = []
    next_available_index = 0
    for event in events:
        index = int(event["index"])
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
    event_scan = _failed_breakout_event_scan(
        candles,
        side=side,
        level_source="rolling_extreme",
        level_lookback_bars=level_lookback_bars,
        level_quality_threshold=0,
        breakout_depth_bps=breakout_depth_bps,
        acceptance_window_bars=acceptance_window_bars,
        acceptance_failure_threshold=0,
        volume_zscore_threshold=volume_zscore_threshold,
    )
    return [int(event["index"]) for event in event_scan["events"]]


def _failed_breakout_event_scan(
    candles: list[OhlcvCandle],
    *,
    side: str,
    level_source: str,
    level_lookback_bars: int,
    level_quality_threshold: float,
    breakout_depth_bps: float,
    acceptance_window_bars: int,
    acceptance_failure_threshold: float,
    volume_zscore_threshold: float,
) -> dict:
    base_candidates = _failed_breakout_base_scan(
        candles,
        side=side,
        level_source=level_source,
        level_lookback_bars=level_lookback_bars,
        acceptance_window_bars=acceptance_window_bars,
    )
    return _failed_breakout_event_scan_from_base(
        base_candidates,
        level_quality_threshold=level_quality_threshold,
        breakout_depth_bps=breakout_depth_bps,
        acceptance_failure_threshold=acceptance_failure_threshold,
        volume_zscore_threshold=volume_zscore_threshold,
    )


def _failed_breakout_base_scan(
    candles: list[OhlcvCandle],
    *,
    side: str,
    level_source: str,
    level_lookback_bars: int,
    acceptance_window_bars: int,
) -> list[dict]:
    base_candidates: list[dict] = []
    start = level_lookback_bars + acceptance_window_bars
    for index in range(start, len(candles)):
        level_window_start = index - acceptance_window_bars - level_lookback_bars + 1
        level_window_end = index - acceptance_window_bars + 1
        level_window = candles[level_window_start:level_window_end]
        recent_window = candles[index - acceptance_window_bars + 1 : index + 1]
        if len(level_window) < level_lookback_bars or len(recent_window) < acceptance_window_bars:
            continue
        candidate_levels = _candidate_failed_breakout_levels(
            candles,
            index,
            side=side,
            level_source=level_source,
            level_window=level_window,
            recent_window=recent_window,
        )
        for candidate in candidate_levels:
            level = float(candidate["level"])
            if side == "short":
                max_breakout_depth_bps = max(0.0, (max(item.high for item in recent_window) / level - 1) * 10000)
                returned_inside = candles[index].close < level
            else:
                max_breakout_depth_bps = max(0.0, (1 - min(item.low for item in recent_window) / level) * 10000)
                returned_inside = candles[index].close > level
            base_candidates.append(
                {
                    "index": index,
                    "level": level,
                    "level_source": str(candidate["level_source"]),
                    "level_quality_score": float(candidate["level_quality_score"]),
                    "max_breakout_depth_bps": max_breakout_depth_bps,
                    "returned_inside": returned_inside,
                    "acceptance_failure_score": _acceptance_failure_score(
                        recent_window,
                        level=level,
                        side=side,
                    ),
                    "volume_zscore": _volume_zscore(candles, index),
                }
            )
    return base_candidates


def _failed_breakout_event_scan_from_base(
    base_candidates: list[dict],
    *,
    level_quality_threshold: float,
    breakout_depth_bps: float,
    acceptance_failure_threshold: float,
    volume_zscore_threshold: float,
) -> dict:
    funnel = {
        "candidate_level_count": 0,
        "quality_pass_count": 0,
        "breakout_count": 0,
        "return_inside_count": 0,
        "acceptance_failure_count": 0,
        "confirmation_count": 0,
        "event_count": 0,
    }
    events_by_index: dict[int, dict] = {}
    funnel["candidate_level_count"] = len(base_candidates)
    for candidate in base_candidates:
        quality_score = float(candidate["level_quality_score"])
        if quality_score < level_quality_threshold:
            continue
        funnel["quality_pass_count"] += 1
        if float(candidate["max_breakout_depth_bps"]) < breakout_depth_bps:
            continue
        funnel["breakout_count"] += 1
        if not bool(candidate["returned_inside"]):
            continue
        funnel["return_inside_count"] += 1
        acceptance_failure_score = float(candidate["acceptance_failure_score"])
        if acceptance_failure_score < acceptance_failure_threshold:
            continue
        funnel["acceptance_failure_count"] += 1
        volume_score = float(candidate["volume_zscore"])
        if volume_zscore_threshold > 0 and volume_score < volume_zscore_threshold:
            continue
        funnel["confirmation_count"] += 1
        event = {
            "index": int(candidate["index"]),
            "level": float(candidate["level"]),
            "level_source": str(candidate["level_source"]),
            "level_quality_score": quality_score,
            "acceptance_failure_score": acceptance_failure_score,
            "volume_zscore": volume_score,
        }
        current = events_by_index.get(int(candidate["index"]))
        current_score = -1 if current is None else float(current["level_quality_score"]) + float(current["acceptance_failure_score"])
        event_score = quality_score + acceptance_failure_score
        if event_score > current_score:
            events_by_index[int(candidate["index"])] = event
    events = [events_by_index[index] for index in sorted(events_by_index)]
    level_source_counts: dict[str, int] = {}
    for event in events:
        source = str(event["level_source"])
        level_source_counts[source] = level_source_counts.get(source, 0) + 1
    funnel["event_count"] = len(events)
    quality_scores = [float(event["level_quality_score"]) for event in events]
    acceptance_scores = [float(event["acceptance_failure_score"]) for event in events]
    return {
        "events": events,
        "funnel": funnel,
        "level_source_counts": level_source_counts,
        "average_level_quality_score": mean(quality_scores) if quality_scores else 0.0,
        "average_acceptance_failure_score": mean(acceptance_scores) if acceptance_scores else 0.0,
    }


def _candidate_failed_breakout_levels(
    candles: list[OhlcvCandle],
    index: int,
    *,
    side: str,
    level_source: str,
    level_window: list[OhlcvCandle],
    recent_window: list[OhlcvCandle],
) -> list[dict[str, float | str]]:
    if not level_window:
        return []
    candidates: list[dict[str, float | str]] = []
    if level_source == "swing_extreme":
        levels = _swing_extreme_levels(level_window, side=side)
    else:
        level = max(item.high for item in level_window) if side == "short" else min(item.low for item in level_window)
        levels = [level]
    for level in levels:
        if level <= 0:
            continue
        quality_score = _level_quality_score(
            level_window,
            level=float(level),
            side=side,
            current_close=candles[index].close,
        )
        candidates.append(
            {
                "level": float(level),
                "level_source": level_source,
                "level_quality_score": quality_score,
            }
        )
    return candidates


def _swing_extreme_levels(
    candles: list[OhlcvCandle],
    *,
    side: str,
    radius: int = 2,
    max_levels: int = 3,
) -> list[float]:
    if len(candles) < radius * 2 + 1:
        return []
    levels: list[float] = []
    for offset in range(radius, len(candles) - radius):
        window = candles[offset - radius : offset + radius + 1]
        candle = candles[offset]
        if side == "short" and candle.high >= max(item.high for item in window):
            levels.append(candle.high)
        elif side == "long" and candle.low <= min(item.low for item in window):
            levels.append(candle.low)
    unique_levels = sorted(set(round(level, 8) for level in levels))
    if side == "short":
        return unique_levels[-max_levels:]
    return unique_levels[:max_levels]


def _level_quality_score(
    candles: list[OhlcvCandle],
    *,
    level: float,
    side: str,
    current_close: float,
) -> float:
    if level <= 0:
        return 0.0
    tolerance = 0.0015
    if side == "short":
        touches = sum(1 for candle in candles if abs(candle.high / level - 1) <= tolerance)
        rejections = sum(1 for candle in candles if candle.high >= level * (1 - tolerance) and candle.close < level)
    else:
        touches = sum(1 for candle in candles if abs(candle.low / level - 1) <= tolerance)
        rejections = sum(1 for candle in candles if candle.low <= level * (1 + tolerance) and candle.close > level)
    distance_bps = abs(current_close / level - 1) * 10000
    touch_score = min(35.0, touches * 7.0)
    rejection_score = min(35.0, rejections * 7.0)
    age_score = min(15.0, len(candles) / 10.0)
    distance_score = max(0.0, 15.0 - min(15.0, distance_bps / 20.0))
    return round(_clamp(touch_score + rejection_score + age_score + distance_score, 0.0, 100.0), 3)


def _acceptance_failure_score(
    candles: list[OhlcvCandle],
    *,
    level: float,
    side: str,
) -> float:
    if not candles or level <= 0:
        return 0.0
    if side == "short":
        outside_close_count = sum(1 for candle in candles if candle.close > level)
        outside_bar_count = sum(1 for candle in candles if candle.high > level)
        breakout_offsets = [offset for offset, candle in enumerate(candles) if candle.high > level]
        wick_bps = max(0.0, (max(candle.high for candle in candles) / level - 1) * 10000)
    else:
        outside_close_count = sum(1 for candle in candles if candle.close < level)
        outside_bar_count = sum(1 for candle in candles if candle.low < level)
        breakout_offsets = [offset for offset, candle in enumerate(candles) if candle.low < level]
        wick_bps = max(0.0, (1 - min(candle.low for candle in candles) / level) * 10000)
    window = len(candles)
    first_breakout_offset = breakout_offsets[0] if breakout_offsets else window - 1
    speed_score = 25.0 * (1 - first_breakout_offset / max(1, window - 1))
    close_score = 40.0 * (1 - outside_close_count / window)
    time_score = 25.0 * (1 - outside_bar_count / window)
    wick_score = min(10.0, wick_bps / 5.0)
    return round(_clamp(close_score + time_score + speed_score + wick_score, 0.0, 100.0), 3)


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
    if best_trial.event_funnel:
        funnel = best_trial.event_funnel
        findings.append(
            "Best-trial funnel: "
            f"levels={funnel.get('candidate_level_count', 0)}, "
            f"quality_pass={funnel.get('quality_pass_count', 0)}, "
            f"breakouts={funnel.get('breakout_count', 0)}, "
            f"returned_inside={funnel.get('return_inside_count', 0)}, "
            f"acceptance_failures={funnel.get('acceptance_failure_count', 0)}, "
            f"confirmed={funnel.get('confirmation_count', 0)}, "
            f"events={funnel.get('event_count', 0)}."
        )
        findings.append(
            "Best-trial scores: "
            f"avg_level_quality={best_trial.average_level_quality_score:.2f}, "
            f"avg_acceptance_failure={best_trial.average_acceptance_failure_score:.2f}."
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


def _parse_threshold_token(value: str) -> float:
    return float(value.replace("m", "-").replace("p", "."))


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_").lower()


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
