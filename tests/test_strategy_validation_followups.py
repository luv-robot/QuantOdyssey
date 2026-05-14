from datetime import datetime, timedelta

from app.models import FailedBreakoutUniverseCell, FailedBreakoutUniverseReport, OhlcvCandle, StrategyFamily
from app.services.harness import (
    parse_failed_breakout_trial_id,
    run_failed_breakout_bootstrap_monte_carlo,
    run_failed_breakout_walk_forward_validation,
    simulate_failed_breakout_trial_returns,
)
from app.storage import QuantRepository


def test_failed_breakout_trial_id_can_be_replayed() -> None:
    trial_id = "trial_short_rolling_extreme_lb24_lq0_d10_aw3_af0_vz1p5"

    params = parse_failed_breakout_trial_id(trial_id)
    returns = simulate_failed_breakout_trial_returns(
        _sample_candles(),
        timeframe="5m",
        trial_id=trial_id,
        horizon_hours=1,
    )

    assert params["side"] == "short"
    assert params["level_lookback_bars"] == 24
    assert params["volume_zscore_threshold"] == 1.5
    assert returns


def test_failed_breakout_walk_forward_and_bootstrap_reports_are_persisted() -> None:
    repository = QuantRepository()
    universe = _universe_report()
    candles_by_cell = {("BTC/USDT:USDT", "5m"): _sample_candles()}

    walk_forward = run_failed_breakout_walk_forward_validation(
        universe_report=universe,
        candles_by_cell=candles_by_cell,
        folds=3,
        min_trades_per_window=1,
        horizon_hours=1,
    )
    monte_carlo = run_failed_breakout_bootstrap_monte_carlo(
        universe_report=universe,
        candles_by_cell=candles_by_cell,
        simulations=30,
        horizon_trades=5,
        seed=7,
        min_sampled_trades=1,
        p05_loss_floor=-1,
        max_probability_of_loss=1,
        max_drawdown_floor=-1,
        horizon_hours=1,
    )

    repository.save_strategy_family_walk_forward_report(walk_forward)
    repository.save_strategy_family_monte_carlo_report(monte_carlo)

    assert walk_forward.completed_windows == 3
    assert any(window.trade_count > 0 for window in walk_forward.windows)
    assert monte_carlo.sampled_trade_count > 0
    assert repository.get_strategy_family_walk_forward_report(walk_forward.report_id) == walk_forward
    assert repository.query_strategy_family_walk_forward_reports(
        source_universe_report_id=universe.report_id
    ) == [walk_forward]
    assert repository.get_strategy_family_monte_carlo_report(monte_carlo.report_id) == monte_carlo
    assert repository.query_strategy_family_monte_carlo_reports(
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value
    ) == [monte_carlo]


def test_failed_breakout_bootstrap_requires_confirmation_when_expensive() -> None:
    report = run_failed_breakout_bootstrap_monte_carlo(
        universe_report=_universe_report(),
        candles_by_cell={("BTC/USDT:USDT", "5m"): _sample_candles()},
        simulations=100,
        horizon_trades=100,
        expensive_simulation_threshold=1,
        approved_to_run=False,
        horizon_hours=1,
    )

    assert report.requires_human_confirmation is True
    assert report.approved_to_run is False
    assert report.passed is False
    assert "human confirmation" in report.findings[0]


def _universe_report() -> FailedBreakoutUniverseReport:
    trial_id = "trial_short_rolling_extreme_lb24_lq0_d10_aw3_af0_vz0"
    return FailedBreakoutUniverseReport(
        report_id="failed_breakout_universe_validation_test",
        thesis_id="thesis_failed_breakout",
        signal_id="signal_failed_breakout",
        strategy_family=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        symbols=["BTC/USDT:USDT"],
        timeframes=["5m"],
        completed_cells=1,
        min_market_confirmations=1,
        robust_trial_ids=[trial_id],
        best_trial_frequency={trial_id: 1},
        cells=[
            FailedBreakoutUniverseCell(
                report_id="failed_breakout_btc_test",
                symbol="BTC/USDT:USDT",
                timeframe="5m",
                completed_trials=1,
                robust_trial_count=1,
                simple_failed_breakout_total_return=-0.01,
                simple_failed_breakout_trade_count=6,
                best_trial_id=trial_id,
                best_trial_trade_count=6,
                best_trial_total_return=0.01,
                best_trial_profit_factor=1.2,
            )
        ],
    )


def _sample_candles(symbol: str = "BTC/USDT:USDT") -> list[OhlcvCandle]:
    start = datetime(2024, 1, 1)
    winning_events = {140, 360, 580}
    losing_events = {250, 470, 690}
    all_events = winning_events | losing_events
    candles: list[OhlcvCandle] = []
    for index in range(740):
        open_time = start + timedelta(minutes=5 * index)
        base = 100 + (index % 20) * 0.01
        close = base
        high = base + 0.3
        low = base - 0.3
        volume = 1000
        if index + 1 in all_events:
            high = 102.0
            close = 101.5
            volume = 1400
        if index in all_events:
            high = 101.8
            close = 100.1
            low = 99.9
            volume = 6000 if index in winning_events else 1000
        for event_index in winning_events:
            if event_index < index <= event_index + 12:
                close = 99.0 - (index - event_index) * 0.02
                high = max(high, close + 0.2)
                low = min(low, close - 0.2)
        for event_index in losing_events:
            if event_index < index <= event_index + 12:
                close = 101.0 + (index - event_index) * 0.02
                high = max(high, close + 0.2)
                low = min(low, close - 0.2)
        open_ = close + 0.03
        high = max(high, open_, close)
        low = min(low, open_, close)
        candles.append(
            OhlcvCandle(
                symbol=symbol,
                interval="5m",
                open_time=open_time,
                close_time=open_time + timedelta(minutes=5),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                quote_volume=volume * close,
                trade_count=100,
                raw=[],
            )
        )
    return candles
