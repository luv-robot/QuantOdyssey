from datetime import datetime

from app.models import BacktestReport, BacktestStatus, MarketSignal, SignalType
from app.services.backtester import compare_to_proxy_baselines


def test_funding_signal_gets_type_specific_proxy_baselines() -> None:
    signal = MarketSignal(
        signal_id="signal_funding_baseline",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="5m",
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=88,
        features={"funding_percentile_30d": 94, "open_interest_percentile_30d": 82},
        hypothesis="funding crowding with failed breakout",
        data_sources=["ohlcv", "funding", "oi"],
    )
    backtest = BacktestReport(
        backtest_id="bt_funding",
        strategy_id="strategy_funding",
        timerange="20240101-20260501",
        trades=120,
        win_rate=0.58,
        profit_factor=1.6,
        sharpe=1.2,
        max_drawdown=-0.07,
        total_return=0.18,
        status=BacktestStatus.PASSED,
    )

    report = compare_to_proxy_baselines(signal, backtest)
    names = {item.name for item in report.baselines}

    assert "funding_extreme_only_proxy" in names
    assert "funding_plus_oi_proxy" in names
    assert "simple_failed_breakout_proxy" in names
    assert "opposite_direction_proxy" in names
    assert report.outperformed_best_baseline is True
    assert any("Funding-crowding baselines" in finding for finding in report.findings)
