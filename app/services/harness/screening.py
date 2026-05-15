from __future__ import annotations

from statistics import mean, pstdev
from uuid import uuid4

from app.models import (
    BaselineImpliedRegimeReport,
    DataSufficiencyGateReport,
    DataSufficiencyLevel,
    FailedBreakoutUniverseReport,
    OhlcvCandle,
    RegimeBucketStats,
    RegimeCoverageReport,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    StrategyFamily,
    StrategyFamilyBaselineBoard,
    StrategyFamilyBaselineRow,
    StrategyScreeningAction,
    StrategyScreeningDecision,
)


DATA_LEVEL_ORDER = {
    DataSufficiencyLevel.L0_OHLCV_ONLY: 0,
    DataSufficiencyLevel.L1_FUNDING_OI: 1,
    DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION: 2,
    DataSufficiencyLevel.L3_ONCHAIN_NARRATIVE: 3,
}


def build_regime_coverage_report(
    candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]],
    *,
    strategy_family: StrategyFamily,
) -> RegimeCoverageReport:
    bucket_returns: dict[str, list[float]] = {}
    bucket_counts: dict[str, int] = {}
    bucket_trends: dict[str, list[float]] = {}
    total = 0
    symbols: set[str] = set()
    timeframes: set[str] = set()

    for (symbol, timeframe), candles in candles_by_cell.items():
        symbols.add(symbol)
        timeframes.add(timeframe)
        sorted_candles = sorted(candles, key=lambda item: item.open_time)
        for index in range(1, len(sorted_candles)):
            previous = sorted_candles[index - 1]
            candle = sorted_candles[index]
            if previous.close <= 0:
                continue
            return_ = candle.close / previous.close - 1
            regime = _ohlcv_regime(sorted_candles, index)
            bucket_returns.setdefault(regime, []).append(return_)
            bucket_counts[regime] = bucket_counts.get(regime, 0) + 1
            bucket_trends.setdefault(regime, []).append(_window_return(sorted_candles, index, 48))
            total += 1

    buckets = [
        RegimeBucketStats(
            regime=regime,
            candle_count=count,
            share=count / total if total else 0,
            average_return=round(mean(bucket_returns[regime]), 8) if bucket_returns.get(regime) else 0,
            realized_volatility=round(pstdev(bucket_returns[regime]), 8)
            if len(bucket_returns.get(regime, [])) > 1
            else 0,
            trend_return=round(mean(bucket_trends[regime]), 6) if bucket_trends.get(regime) else 0,
        )
        for regime, count in sorted(bucket_counts.items())
    ]
    dominant = max(buckets, key=lambda item: item.share, default=None)
    balanced = bool(buckets) and (dominant is None or dominant.share <= 0.7) and len(buckets) >= 3
    findings = [f"Regime coverage includes {len(buckets)} bucket(s) over {total} candle transition(s)."]
    if dominant is not None:
        findings.append(f"Dominant regime is {dominant.regime} at {dominant.share:.1%} coverage.")
    if not balanced:
        findings.append("Coverage is not balanced enough for strong cross-regime conclusions.")

    return RegimeCoverageReport(
        report_id=f"regime_coverage_{uuid4().hex[:8]}",
        strategy_family=strategy_family.value,
        symbols=sorted(symbols),
        timeframes=sorted(timeframes),
        buckets=buckets,
        is_coverage_balanced=balanced,
        dominant_regime=None if dominant is None else dominant.regime,
        findings=findings,
    )


def build_strategy_family_baseline_board(
    candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]],
    *,
    failed_breakout_report: FailedBreakoutUniverseReport | None = None,
) -> StrategyFamilyBaselineBoard:
    rows = [
        _cash_row(),
        _passive_btc_row(candles_by_cell, mode="buy_and_hold"),
        _passive_btc_row(candles_by_cell, mode="dca"),
        _equal_weight_hold_row(candles_by_cell),
        _cross_sectional_momentum_row(candles_by_cell),
        _time_series_trend_row(candles_by_cell),
        _breakout_trend_row(candles_by_cell),
        _mean_reversion_row(candles_by_cell),
        _grid_range_row(candles_by_cell),
    ]

    best = max(rows, key=lambda item: (item.total_return, item.profit_factor), default=None)
    findings = [
        "Baseline board covers passive exposure, momentum, trend following, and range/grid proxies.",
        "Passive BTC exposure baselines include both buy-and-hold BTC and DCA BTC.",
    ]
    if best is not None:
        findings.append(f"Best baseline family is {best.strategy_family} with return {best.total_return:.4f}.")
    if failed_breakout_report is not None:
        findings.append("Failed Breakout is candidate evidence and is intentionally excluded from generic baselines.")

    return StrategyFamilyBaselineBoard(
        board_id=f"strategy_family_baseline_board_{uuid4().hex[:8]}",
        symbols=sorted({symbol for symbol, _ in candles_by_cell}),
        timeframes=sorted({timeframe for _, timeframe in candles_by_cell}),
        rows=rows,
        best_family=None if best is None else best.strategy_family,
        findings=findings,
    )


def build_baseline_implied_regime_report(board: StrategyFamilyBaselineBoard) -> BaselineImpliedRegimeReport:
    """Infer a provisional regime from generic baseline performance.

    This is intentionally a reverse-inference diagnostic: it says which simple
    strategy class the current data window rewarded. It is not a standalone
    regime classifier and should later be checked against independent regime features.
    """
    rows_by_name = {row.strategy_family: row for row in board.rows}
    row_scores = {row.strategy_family: _baseline_strength(row) for row in board.rows}
    component_scores = {
        "passive_beta": _max_score(
            row_scores,
            "passive_btc_buy_and_hold",
            "passive_btc_dca",
            "passive_equal_weight_buy_and_hold",
        ),
        "directional_momentum": _max_score(row_scores, "cross_sectional_momentum"),
        "trend_following": _max_score(row_scores, "time_series_trend", "breakout_trend"),
        "range_harvesting": _max_score(row_scores, "range_mean_reversion", "grid_range"),
        "defensive_cash": _defensive_score(board.rows),
    }
    ranked_components = sorted(component_scores.items(), key=lambda item: (-item[1], item[0]))
    top_name, top_score = ranked_components[0] if ranked_components else ("mixed_or_transition", 0.0)
    second_score = ranked_components[1][1] if len(ranked_components) > 1 else 0.0
    gap = top_score - second_score
    regime_label = _regime_label_from_components(component_scores, gap)
    confidence = round(min(0.9, max(0.35, 0.4 + gap / 100)), 3)
    leaders = [
        name
        for name, _ in sorted(row_scores.items(), key=lambda item: (-item[1], item[0]))[:3]
        if name in rows_by_name
    ]
    laggards = [
        name
        for name, _ in sorted(row_scores.items(), key=lambda item: (item[1], item[0]))[:3]
        if name in rows_by_name
    ]
    findings = [
        f"Baseline-implied regime is {regime_label} with {confidence:.1%} confidence.",
        f"Top component is {top_name} at score {top_score:.2f}; runner-up score is {second_score:.2f}.",
        f"Leading baseline(s): {', '.join(leaders) if leaders else 'none'}.",
        "This is a provisional reverse inference from baseline outcomes, not an independent regime model.",
    ]
    return BaselineImpliedRegimeReport(
        report_id=f"baseline_implied_regime_{uuid4().hex[:8]}",
        source_baseline_board_id=board.board_id,
        regime_label=regime_label,
        confidence=confidence,
        component_scores={key: round(value, 3) for key, value in component_scores.items()},
        leading_baselines=leaders,
        lagging_baselines=laggards,
        findings=findings,
    )


def build_data_sufficiency_gate(
    *,
    strategy_family: StrategyFamily,
    available_level: DataSufficiencyLevel,
    minimum_validation_level: DataSufficiencyLevel | None = None,
    missing_evidence: list[str] | None = None,
) -> DataSufficiencyGateReport:
    minimum = minimum_validation_level or _minimum_data_level(strategy_family)
    recommended = _recommended_next_level(strategy_family, available_level)
    can_continue = DATA_LEVEL_ORDER[available_level] >= DATA_LEVEL_ORDER[minimum]
    should_upgrade = DATA_LEVEL_ORDER[available_level] < DATA_LEVEL_ORDER[recommended]
    gaps = list(dict.fromkeys(missing_evidence or []))
    if should_upgrade and strategy_family == StrategyFamily.FAILED_BREAKOUT_PUNISHMENT:
        gaps.extend(["aggTrades/CVD needed to judge breakout acceptance", "tick-derived aggressive-flow efficiency"])
    findings = [
        f"Available data level is {available_level.value}; minimum validation level is {minimum.value}.",
        "Current evidence can support a first-pass screen." if can_continue else "Current evidence cannot support validation.",
    ]
    if should_upgrade:
        findings.append(f"Recommended next data level is {recommended.value}.")
    return DataSufficiencyGateReport(
        gate_id=f"data_sufficiency_gate_{uuid4().hex[:8]}",
        strategy_family=strategy_family.value,
        available_level=available_level,
        minimum_validation_level=minimum,
        recommended_next_level=recommended,
        can_continue=can_continue,
        should_upgrade_data=should_upgrade,
        missing_evidence=list(dict.fromkeys(gaps)),
        findings=findings,
    )


def decide_strategy_screening_action(
    *,
    strategy_family: StrategyFamily,
    universe_report: FailedBreakoutUniverseReport | None,
    regime_coverage: RegimeCoverageReport | None,
    baseline_board: StrategyFamilyBaselineBoard | None,
    data_gate: DataSufficiencyGateReport,
) -> StrategyScreeningDecision:
    rationale: list[str] = []
    evidence_refs: list[str] = [f"data_sufficiency_gate:{data_gate.gate_id}"]
    tasks: list[ResearchTask] = []
    action = StrategyScreeningAction.ROTATE_STRATEGY_FAMILY
    confidence = 0.55

    if universe_report is not None:
        evidence_refs.append(f"failed_breakout_universe_report:{universe_report.report_id}")
        positive_cells = sum(1 for cell in universe_report.cells if cell.best_trial_total_return > 0)
        sufficient_cells = sum(1 for cell in universe_report.cells if cell.best_trial_trade_count >= 80)
        rationale.append(f"{positive_cells}/{len(universe_report.cells)} universe cell(s) had positive best trials.")
        rationale.append(f"{sufficient_cells}/{len(universe_report.cells)} universe cell(s) met the 80-trade maturity reference.")
    else:
        positive_cells = 0
        sufficient_cells = 0

    if regime_coverage is not None:
        evidence_refs.append(f"regime_coverage_report:{regime_coverage.report_id}")
        rationale.extend(regime_coverage.findings)
    if baseline_board is not None:
        evidence_refs.append(f"strategy_family_baseline_board:{baseline_board.board_id}")
        rationale.extend(baseline_board.findings)

    if not data_gate.can_continue:
        action = StrategyScreeningAction.UPGRADE_DATA
        confidence = 0.8
        tasks.append(_data_upgrade_task(strategy_family, data_gate, priority=90))
    elif data_gate.should_upgrade_data and positive_cells > 0 and sufficient_cells == 0:
        action = StrategyScreeningAction.UPGRADE_DATA
        confidence = 0.72
        tasks.append(_data_upgrade_task(strategy_family, data_gate, priority=86))
    elif positive_cells >= 2 and sufficient_cells >= 1:
        action = StrategyScreeningAction.DEEPEN_VALIDATION
        confidence = 0.74
        tasks.extend(_deepen_validation_tasks(strategy_family, universe_report))
    elif positive_cells > 0:
        action = StrategyScreeningAction.NEEDS_MORE_COVERAGE
        confidence = 0.64
        tasks.append(_coverage_task(strategy_family, universe_report))
    elif universe_report is not None:
        action = StrategyScreeningAction.RECORD_FAILURE
        confidence = 0.7
        tasks.append(_failure_memory_task(strategy_family, universe_report))

    return StrategyScreeningDecision(
        decision_id=f"strategy_screening_decision_{uuid4().hex[:8]}",
        strategy_family=strategy_family.value,
        action=action,
        confidence=confidence,
        rationale=rationale,
        next_tasks=tasks,
        evidence_refs=evidence_refs,
    )


def _ohlcv_regime(candles: list[OhlcvCandle], index: int) -> str:
    trend = abs(_window_return(candles, index, 48))
    volatility = _window_volatility(candles, index, 48)
    if volatility >= 0.012:
        return "high_volatility"
    if trend >= 0.03:
        return "trend"
    if volatility <= 0.003:
        return "low_volatility"
    return "range"


def _window_return(candles: list[OhlcvCandle], index: int, lookback: int) -> float:
    start = max(0, index - lookback)
    if candles[start].close <= 0:
        return 0
    return candles[index].close / candles[start].close - 1


def _window_volatility(candles: list[OhlcvCandle], index: int, lookback: int) -> float:
    start = max(1, index - lookback + 1)
    returns = [
        candles[offset].close / candles[offset - 1].close - 1
        for offset in range(start, index + 1)
        if candles[offset - 1].close > 0
    ]
    return pstdev(returns) if len(returns) > 1 else 0


def _cash_row() -> StrategyFamilyBaselineRow:
    return StrategyFamilyBaselineRow(
        strategy_family="cash_no_trade",
        description="No-position cash baseline.",
        total_return=0,
        profit_factor=1,
        sharpe=None,
        max_drawdown=0,
        trades=0,
        positive_cell_count=0,
        tested_cell_count=0,
    )


def _passive_btc_row(candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]], *, mode: str) -> StrategyFamilyBaselineRow:
    btc_cells = [(cell, candles) for cell, candles in candles_by_cell.items() if cell[0].upper().startswith("BTC/")]
    returns: list[float] = []
    for _, candles in btc_cells:
        sorted_candles = sorted(candles, key=lambda item: item.open_time)
        if len(sorted_candles) < 2:
            continue
        if mode == "dca":
            returns.append(_dca_return(sorted_candles))
        else:
            returns.append(sorted_candles[-1].close / sorted_candles[0].close - 1)
    total_return = mean(returns) if returns else 0
    name = "passive_btc_dca" if mode == "dca" else "passive_btc_buy_and_hold"
    description = (
        "Equal-cash periodic BTC accumulation baseline."
        if mode == "dca"
        else "Buy-and-hold BTC passive exposure baseline."
    )
    return StrategyFamilyBaselineRow(
        strategy_family=name,
        description=description,
        total_return=round(total_return, 6),
        profit_factor=1.0 if total_return > 0 else 0,
        sharpe=None,
        max_drawdown=round(min(total_return, 0), 6),
        trades=len(returns),
        positive_cell_count=sum(1 for item in returns if item > 0),
        tested_cell_count=len(returns),
    )


def _equal_weight_hold_row(candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]]) -> StrategyFamilyBaselineRow:
    returns: list[float] = []
    for candles in candles_by_cell.values():
        sorted_candles = sorted(candles, key=lambda item: item.open_time)
        if len(sorted_candles) >= 2 and sorted_candles[0].close > 0:
            returns.append(sorted_candles[-1].close / sorted_candles[0].close - 1)
    return _row_from_returns(
        "passive_equal_weight_buy_and_hold",
        "Equal-weight passive buy-and-hold across available symbols/timeframes.",
        returns,
    )


def _dca_return(candles: list[OhlcvCandle], steps: int = 12) -> float:
    if len(candles) < 2:
        return 0
    interval = max(1, len(candles) // steps)
    units = 0.0
    invested = 0.0
    for candle in candles[::interval]:
        units += 1.0 / candle.close
        invested += 1.0
    if invested == 0:
        return 0
    return units * candles[-1].close / invested - 1


def _cross_sectional_momentum_row(
    candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]],
    *,
    lookback: int = 48,
    horizon: int = 12,
) -> StrategyFamilyBaselineRow:
    returns: list[float] = []
    for _, group in _cells_by_timeframe(candles_by_cell).items():
        sorted_group = [(symbol, sorted(candles, key=lambda item: item.open_time)) for symbol, candles in group]
        if not sorted_group:
            continue
        max_len = min(len(candles) for _, candles in sorted_group)
        index = lookback
        while index + horizon < max_len:
            ranked = []
            for symbol, candles in sorted_group:
                if candles[index - lookback].close <= 0 or candles[index].close <= 0:
                    continue
                ranked.append((candles[index].close / candles[index - lookback].close - 1, symbol, candles))
            if ranked:
                _, _, chosen = max(ranked, key=lambda item: item[0])
                entry = chosen[index].close
                exit_ = chosen[index + horizon].close
                if entry > 0:
                    returns.append(exit_ / entry - 1)
                index += horizon
            else:
                index += 1
    return _row_from_returns(
        "cross_sectional_momentum",
        "Cross-sectional momentum baseline: hold the strongest recent asset for a fixed horizon.",
        returns,
    )


def _time_series_trend_row(candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]]) -> StrategyFamilyBaselineRow:
    returns = [
        _fixed_horizon_signal_return(candles, side="long", mode="momentum", lookback=96, horizon=24)
        for candles in candles_by_cell.values()
    ]
    return _row_from_returns(
        "time_series_trend",
        "Time-series trend baseline using positive trailing return as a long signal.",
        returns,
    )


def _breakout_trend_row(
    candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]],
    *,
    lookback: int = 96,
    horizon: int = 24,
) -> StrategyFamilyBaselineRow:
    returns = [_donchian_breakout_return(candles, lookback=lookback, horizon=horizon) for candles in candles_by_cell.values()]
    return _row_from_returns(
        "breakout_trend",
        "Donchian-style breakout trend baseline.",
        returns,
    )


def _mean_reversion_row(candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]]) -> StrategyFamilyBaselineRow:
    returns = [_fixed_horizon_signal_return(candles, side="long", mode="mean_reversion") for candles in candles_by_cell.values()]
    return _row_from_returns("range_mean_reversion", "Simple OHLCV range mean-reversion baseline.", returns)


def _grid_range_row(candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]]) -> StrategyFamilyBaselineRow:
    returns = [_grid_proxy_return(candles) for candles in candles_by_cell.values()]
    return _row_from_returns(
        "grid_range",
        "Range-harvesting grid proxy using rolling midline deviations with bounded inventory.",
        returns,
    )


def _fixed_horizon_signal_return(candles: list[OhlcvCandle], *, side: str, mode: str, lookback: int = 48, horizon: int = 12) -> float:
    sorted_candles = sorted(candles, key=lambda item: item.open_time)
    returns: list[float] = []
    index = lookback
    while index + horizon < len(sorted_candles):
        window_return = _window_return(sorted_candles, index, lookback)
        if mode == "momentum":
            enter = window_return > 0.015
        else:
            enter = window_return < -0.015
        if enter:
            entry = sorted_candles[index].close
            exit_ = sorted_candles[index + horizon].close
            if entry > 0:
                returns.append(exit_ / entry - 1 if side == "long" else entry / exit_ - 1)
            index += horizon
        else:
            index += 1
    return sum(returns)


def _donchian_breakout_return(candles: list[OhlcvCandle], *, lookback: int, horizon: int) -> float:
    sorted_candles = sorted(candles, key=lambda item: item.open_time)
    returns: list[float] = []
    index = lookback
    while index + horizon < len(sorted_candles):
        previous_high = max(item.high for item in sorted_candles[index - lookback : index])
        if sorted_candles[index].close > previous_high and sorted_candles[index].close > 0:
            returns.append(sorted_candles[index + horizon].close / sorted_candles[index].close - 1)
            index += horizon
        else:
            index += 1
    return sum(returns)


def _grid_proxy_return(candles: list[OhlcvCandle], *, lookback: int = 48, horizon: int = 6) -> float:
    sorted_candles = sorted(candles, key=lambda item: item.open_time)
    returns: list[float] = []
    index = lookback
    while index + horizon < len(sorted_candles):
        window = sorted_candles[index - lookback : index]
        midpoint = mean([item.close for item in window])
        volatility = pstdev([item.close / window[offset - 1].close - 1 for offset, item in enumerate(window[1:], start=1)])
        threshold = max(0.005, volatility * 2)
        close = sorted_candles[index].close
        if midpoint <= 0 or close <= 0:
            index += 1
            continue
        distance = close / midpoint - 1
        if distance <= -threshold:
            returns.append(sorted_candles[index + horizon].close / close - 1)
            index += horizon
        elif distance >= threshold:
            returns.append(close / sorted_candles[index + horizon].close - 1)
            index += horizon
        else:
            index += 1
    return sum(returns)


def _cells_by_timeframe(
    candles_by_cell: dict[tuple[str, str], list[OhlcvCandle]],
) -> dict[str, list[tuple[str, list[OhlcvCandle]]]]:
    groups: dict[str, list[tuple[str, list[OhlcvCandle]]]] = {}
    for (symbol, timeframe), candles in candles_by_cell.items():
        groups.setdefault(timeframe, []).append((symbol, candles))
    return groups


def _row_from_returns(strategy_family: str, description: str, returns: list[float]) -> StrategyFamilyBaselineRow:
    usable = [item for item in returns if item != 0]
    total_return = mean(returns) if returns else 0
    gross_profit = sum(item for item in usable if item > 0)
    gross_loss = abs(sum(item for item in usable if item < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
    return StrategyFamilyBaselineRow(
        strategy_family=strategy_family,
        description=description,
        total_return=round(total_return, 6),
        profit_factor=round(profit_factor, 6),
        sharpe=round(mean(usable) / pstdev(usable), 6) if len(usable) > 1 and pstdev(usable) > 0 else None,
        max_drawdown=round(min(min(usable or [0]), 0), 6),
        trades=len(usable),
        positive_cell_count=sum(1 for item in returns if item > 0),
        tested_cell_count=len(returns),
    )


def _baseline_strength(row: StrategyFamilyBaselineRow) -> float:
    return_component = row.total_return * 240
    pf_component = (min(row.profit_factor, 3.0) - 1.0) * 12 if row.profit_factor > 0 else -12
    sharpe_component = 0 if row.sharpe is None else max(-10, min(20, row.sharpe * 8))
    drawdown_component = -abs(row.max_drawdown) * 120
    breadth = row.positive_cell_count / row.tested_cell_count if row.tested_cell_count else 0
    sample_component = min(10, row.trades / 80 * 10)
    return _clamp(50 + return_component + pf_component + sharpe_component + drawdown_component + breadth * 10 + sample_component)


def _max_score(scores: dict[str, float], *names: str) -> float:
    return max((scores.get(name, 0.0) for name in names), default=0.0)


def _defensive_score(rows: list[StrategyFamilyBaselineRow]) -> float:
    active_returns = [row.total_return for row in rows if row.strategy_family != "cash_no_trade"]
    best_active = max(active_returns, default=0.0)
    worst_drawdown = min((row.max_drawdown for row in rows if row.strategy_family != "cash_no_trade"), default=0.0)
    if best_active <= 0:
        return _clamp(75 + abs(worst_drawdown) * 50)
    return _clamp(55 - best_active * 180 + abs(worst_drawdown) * 25)


def _regime_label_from_components(component_scores: dict[str, float], gap: float) -> str:
    top_name, top_score = max(component_scores.items(), key=lambda item: item[1])
    if gap < 6:
        return "mixed_or_transition"
    if top_name == "defensive_cash" and top_score >= 55:
        return "risk_off_or_low_edge"
    if top_name == "passive_beta":
        return "beta_trend"
    if top_name in {"directional_momentum", "trend_following"}:
        return "directional_trend"
    if top_name == "range_harvesting":
        return "range_or_mean_reverting"
    return "mixed_or_transition"


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, round(value, 6)))


def _failed_breakout_row(report: FailedBreakoutUniverseReport) -> StrategyFamilyBaselineRow:
    returns = [cell.best_trial_total_return for cell in report.cells]
    total_return = mean(returns) if returns else 0
    best_pfs = [cell.best_trial_profit_factor for cell in report.cells if cell.best_trial_profit_factor > 0]
    return StrategyFamilyBaselineRow(
        strategy_family=report.strategy_family,
        description="Best Failed Breakout universe-scan trial per market/timeframe cell.",
        total_return=round(total_return, 6),
        profit_factor=round(mean(best_pfs), 6) if best_pfs else 0,
        sharpe=None,
        max_drawdown=round(min(returns or [0]), 6),
        trades=sum(cell.best_trial_trade_count for cell in report.cells),
        positive_cell_count=sum(1 for item in returns if item > 0),
        tested_cell_count=len(returns),
    )


def _minimum_data_level(strategy_family: StrategyFamily) -> DataSufficiencyLevel:
    if strategy_family == StrategyFamily.FUNDING_CROWDING_FADE:
        return DataSufficiencyLevel.L1_FUNDING_OI
    return DataSufficiencyLevel.L0_OHLCV_ONLY


def _recommended_next_level(strategy_family: StrategyFamily, available_level: DataSufficiencyLevel) -> DataSufficiencyLevel:
    if strategy_family == StrategyFamily.FAILED_BREAKOUT_PUNISHMENT:
        return DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION
    if strategy_family == StrategyFamily.FUNDING_CROWDING_FADE:
        return DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION
    return available_level


def _deepen_validation_tasks(
    strategy_family: StrategyFamily,
    report: FailedBreakoutUniverseReport | None,
) -> list[ResearchTask]:
    subject_id = strategy_family.value
    evidence_refs = [] if report is None else [f"failed_breakout_universe_report:{report.report_id}"]
    return [
        ResearchTask(
            task_id=f"task_walk_forward_{subject_id}_{uuid4().hex[:8]}",
            task_type=ResearchTaskType.WALK_FORWARD_TEST,
            subject_type="strategy_family",
            subject_id=subject_id,
            thesis_id=None if report is None else report.thesis_id,
            signal_id=None if report is None else report.signal_id,
            hypothesis="Promising cells should survive walk-forward splits before any optimization.",
            rationale="Universe screening found positive cells with enough sample to justify deeper validation.",
            required_experiments=["walk-forward split by time", "compare in-sample and out-of-sample PF/Sharpe"],
            success_metrics=["OOS PF > 1.1", "OOS trade count remains above sample floor"],
            failure_conditions=["OOS return collapses", "single period explains most profit"],
            required_data_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
            estimated_cost=55,
            priority_score=84,
            status=ResearchTaskStatus.PROPOSED,
            evidence_refs=evidence_refs,
        ),
        ResearchTask(
            task_id=f"task_monte_carlo_{subject_id}_{uuid4().hex[:8]}",
            task_type=ResearchTaskType.MONTE_CARLO_TEST,
            subject_type="strategy_family",
            subject_id=subject_id,
            thesis_id=None if report is None else report.thesis_id,
            signal_id=None if report is None else report.signal_id,
            hypothesis="Promising cells should retain acceptable path risk under trade-order resampling.",
            rationale="Screening is not enough to judge path dependency or drawdown clustering.",
            required_experiments=["trade-level bootstrap", "block bootstrap if trades are clustered"],
            success_metrics=["median return > 0", "p05 loss within risk budget"],
            failure_conditions=["loss probability remains high"],
            required_data_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
            estimated_cost=45,
            priority_score=78,
            status=ResearchTaskStatus.PROPOSED,
            evidence_refs=evidence_refs,
        ),
    ]


def _data_upgrade_task(
    strategy_family: StrategyFamily,
    gate: DataSufficiencyGateReport,
    *,
    priority: float,
) -> ResearchTask:
    return ResearchTask(
        task_id=f"task_data_upgrade_{strategy_family.value}_{uuid4().hex[:8]}",
        task_type=ResearchTaskType.DATA_SUFFICIENCY_REVIEW,
        subject_type="strategy_family",
        subject_id=strategy_family.value,
        hypothesis="Further progress requires upgrading the data layer before tuning this strategy family.",
        rationale="Data sufficiency gate indicates missing evidence for the current strategy family.",
        required_experiments=gate.missing_evidence or ["audit available market data"],
        success_metrics=[f"available_level >= {gate.recommended_next_level.value}"],
        failure_conditions=["required data cannot be acquired at acceptable cost"],
        required_data_level=gate.recommended_next_level,
        estimated_cost=40,
        priority_score=priority,
        status=ResearchTaskStatus.PROPOSED,
        evidence_refs=[f"data_sufficiency_gate:{gate.gate_id}"],
    )


def _coverage_task(
    strategy_family: StrategyFamily,
    report: FailedBreakoutUniverseReport | None,
) -> ResearchTask:
    return ResearchTask(
        task_id=f"task_more_coverage_{strategy_family.value}_{uuid4().hex[:8]}",
        task_type=ResearchTaskType.CROSS_SYMBOL_TEST,
        subject_type="strategy_family",
        subject_id=strategy_family.value,
        thesis_id=None if report is None else report.thesis_id,
        signal_id=None if report is None else report.signal_id,
        hypothesis="Promising but under-sampled cells need broader coverage before deeper validation.",
        rationale="Universe screening found positive evidence, but trade samples are below maturity thresholds.",
        required_experiments=["expand symbol/timeframe coverage", "run fast grid before smoke/full grid"],
        success_metrics=["at least two cells exceed 80 trades", "same trial id appears across multiple cells"],
        failure_conditions=["sample count remains too low", "best trials are isolated by symbol"],
        required_data_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
        estimated_cost=35,
        priority_score=76,
        status=ResearchTaskStatus.PROPOSED,
        evidence_refs=[] if report is None else [f"failed_breakout_universe_report:{report.report_id}"],
    )


def _failure_memory_task(
    strategy_family: StrategyFamily,
    report: FailedBreakoutUniverseReport,
) -> ResearchTask:
    return ResearchTask(
        task_id=f"task_failure_memory_{strategy_family.value}_{uuid4().hex[:8]}",
        task_type=ResearchTaskType.FAILURE_CLUSTER_REVIEW,
        subject_type="strategy_family",
        subject_id=strategy_family.value,
        thesis_id=report.thesis_id,
        signal_id=report.signal_id,
        hypothesis="Failed universe scans should become reusable negative evidence before rotating strategy families.",
        rationale="No positive universe cells were found under the current screen.",
        required_experiments=["summarize failed cells", "record market/timeframe exclusions"],
        success_metrics=["failure case is searchable", "next harness cycle avoids repeating the same test"],
        failure_conditions=["failure reason remains ambiguous"],
        required_data_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
        estimated_cost=10,
        priority_score=65,
        status=ResearchTaskStatus.PROPOSED,
        evidence_refs=[f"failed_breakout_universe_report:{report.report_id}"],
    )
