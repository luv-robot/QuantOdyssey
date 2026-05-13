from app.models import BacktestReport, BacktestStatus
from app.services.backtester.validation_suite import run_cross_symbol_validation
from tests.test_models import sample_manifest


def test_cross_symbol_validation_classifies_primary_related_and_stress(monkeypatch) -> None:
    source = BacktestReport(
        backtest_id="backtest_strategy_001",
        strategy_id="strategy_001",
        timerange="20240101-20260501",
        trades=100,
        win_rate=0.55,
        profit_factor=1.4,
        sharpe=1.1,
        max_drawdown=-0.06,
        total_return=0.2,
        status=BacktestStatus.PASSED,
    )

    def fake_run(manifest, timerange, config_path, userdir, timeout_seconds, pairs, backtest_id_suffix):
        symbol = pairs[0]
        status = BacktestStatus.PASSED if symbol != "DOGE/USDT" else BacktestStatus.FAILED
        return (
            source.model_copy(
                update={
                    "backtest_id": f"backtest_{symbol.replace('/', '_')}",
                    "status": status,
                    "profit_factor": 1.3 if status == BacktestStatus.PASSED else 0.8,
                    "error": None if status == BacktestStatus.PASSED else "failed",
                }
            ),
            [],
            {},
        )

    monkeypatch.setattr("app.services.backtester.validation_suite.run_freqtrade_backtest", fake_run)

    report = run_cross_symbol_validation(
        manifest=sample_manifest(),
        source_backtest=source,
        primary_symbol="BTC/USDT",
        related_symbols=["ETH/USDT"],
        stress_symbols=["DOGE/USDT"],
        config_path="configs/freqtrade_config.json",
        userdir="freqtrade_user_data",
        timeout_seconds=1,
    )

    assert report.passed is True
    assert report.pass_rate == 0.666667
    assert {item.classification for item in report.results} == {"primary", "related", "stress"}
