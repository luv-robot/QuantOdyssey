from pathlib import Path
import json
import zipfile

from app.models import BacktestStatus
from app.models import StrategyManifest
from app.services.backtester import (
    build_backtest_command,
    build_backtest_preflight,
    extract_freqtrade_trades,
    find_latest_backtest_result,
    load_freqtrade_trading_mode,
    load_freqtrade_result,
    parse_freqtrade_result_json,
    parse_strategy_name,
    strategy_allows_short,
)


def test_parse_strategy_name_from_freqtrade_file(tmp_path) -> None:
    strategy_file = tmp_path / "ExampleStrategy.py"
    strategy_file.write_text(
        "from freqtrade.strategy import IStrategy\n\nclass ExampleStrategy(IStrategy):\n    pass\n",
        encoding="utf-8",
    )

    assert parse_strategy_name(strategy_file) == "ExampleStrategy"


def test_strategy_allows_short_detects_can_short(tmp_path) -> None:
    strategy_file = tmp_path / "ShortStrategy.py"
    strategy_file.write_text(
        "from freqtrade.strategy import IStrategy\n\nclass ShortStrategy(IStrategy):\n"
        "    can_short = True\n",
        encoding="utf-8",
    )

    assert strategy_allows_short(strategy_file) is True


def test_build_backtest_command() -> None:
    command = build_backtest_command(
        strategy_name="ExampleStrategy",
        timerange="20240101-20260501",
        config_path=Path("configs/freqtrade_config.json"),
        userdir=Path("freqtrade_user_data"),
    )

    assert command == [
        "freqtrade",
        "backtesting",
        "--strategy",
        "ExampleStrategy",
        "--config",
        "configs/freqtrade_config.json",
        "--userdir",
        "freqtrade_user_data",
        "--timerange",
        "20240101-20260501",
        "--export",
        "trades",
    ]


def test_build_backtest_command_accepts_pair_override() -> None:
    command = build_backtest_command(
        strategy_name="ExampleStrategy",
        timerange="20240101-20260501",
        pairs=["ETH/USDT", "SOL/USDT"],
    )

    assert "--pairs" in command
    assert command[command.index("--pairs") + 1 : command.index("--pairs") + 3] == [
        "ETH/USDT",
        "SOL/USDT",
    ]


def test_load_freqtrade_trading_mode_defaults_to_spot_for_missing_file(tmp_path) -> None:
    assert load_freqtrade_trading_mode(tmp_path / "missing.json") == "missing"


def test_backtest_preflight_blocks_short_strategy_on_spot_config(tmp_path) -> None:
    strategy_file = tmp_path / "ShortStrategy.py"
    strategy_file.write_text(
        "from freqtrade.strategy import IStrategy\n\nclass ShortStrategy(IStrategy):\n"
        "    timeframe = '5m'\n"
        "    can_short = True\n",
        encoding="utf-8",
    )
    config = tmp_path / "spot.json"
    config.write_text('{"trading_mode": "spot"}', encoding="utf-8")
    data_file = tmp_path / "user_data" / "data" / "binance" / "BTC_USDT-5m.feather"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("", encoding="utf-8")
    manifest = StrategyManifest(
        strategy_id="strategy_short",
        signal_id="signal_001",
        name="ShortStrategy",
        file_path=str(strategy_file),
        generated_at="2026-05-14T00:00:00",
        timeframe="5m",
        symbols=["BTC/USDT"],
        assumptions=["short test"],
        failure_modes=["spot mode"],
    )

    preflight = build_backtest_preflight(
        manifest=manifest,
        strategy_file=strategy_file,
        config_path=config,
        userdir=tmp_path / "user_data",
        timerange="20240101-20260501",
        pairs=["BTC/USDT"],
    )

    assert preflight["ok"] is False
    assert "strategy has can_short=True but selected config is not futures" in preflight["errors"]


def test_backtest_preflight_accepts_futures_data_for_short_strategy(tmp_path) -> None:
    strategy_file = tmp_path / "ShortStrategy.py"
    strategy_file.write_text(
        "from freqtrade.strategy import IStrategy\n\nclass ShortStrategy(IStrategy):\n"
        "    timeframe = '5m'\n"
        "    can_short = True\n",
        encoding="utf-8",
    )
    config = tmp_path / "futures.json"
    config.write_text('{"trading_mode": "futures"}', encoding="utf-8")
    data_file = tmp_path / "user_data" / "data" / "binance" / "BTC_USDT_USDT-5m.feather"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("", encoding="utf-8")
    manifest = StrategyManifest(
        strategy_id="strategy_short",
        signal_id="signal_001",
        name="ShortStrategy",
        file_path=str(strategy_file),
        generated_at="2026-05-14T00:00:00",
        timeframe="5m",
        symbols=["BTC/USDT:USDT"],
        assumptions=["short test"],
        failure_modes=["missing data"],
    )

    preflight = build_backtest_preflight(
        manifest=manifest,
        strategy_file=strategy_file,
        config_path=config,
        userdir=tmp_path / "user_data",
        timerange="20240101-20260501",
        pairs=["BTC/USDT:USDT"],
    )

    assert preflight["ok"] is True
    assert preflight["trading_mode"] == "futures"
    assert preflight["data_checks"][0]["found_path"] == str(data_file)


def test_backtest_preflight_requires_exact_futures_timeframe(tmp_path) -> None:
    strategy_file = tmp_path / "ShortStrategy.py"
    strategy_file.write_text(
        "from freqtrade.strategy import IStrategy\n\nclass ShortStrategy(IStrategy):\n"
        "    timeframe = '5m'\n"
        "    can_short = True\n",
        encoding="utf-8",
    )
    config = tmp_path / "futures.json"
    config.write_text('{"trading_mode": "futures"}', encoding="utf-8")
    data_file = tmp_path / "user_data" / "data" / "binance" / "futures" / "BTC_USDT_USDT-15m-futures.feather"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("", encoding="utf-8")
    manifest = StrategyManifest(
        strategy_id="strategy_short",
        signal_id="signal_001",
        name="ShortStrategy",
        file_path=str(strategy_file),
        generated_at="2026-05-14T00:00:00",
        timeframe="5m",
        symbols=["BTC/USDT:USDT"],
        assumptions=["short test"],
        failure_modes=["missing data"],
    )

    preflight = build_backtest_preflight(
        manifest=manifest,
        strategy_file=strategy_file,
        config_path=config,
        userdir=tmp_path / "user_data",
        timerange="20240101-20260501",
        pairs=["BTC/USDT:USDT"],
    )

    assert preflight["ok"] is False
    assert preflight["data_checks"][0]["found_path"] is None


def test_backtest_preflight_rejects_futures_mark_and_funding_files(tmp_path) -> None:
    strategy_file = tmp_path / "ShortStrategy.py"
    strategy_file.write_text(
        "from freqtrade.strategy import IStrategy\n\nclass ShortStrategy(IStrategy):\n"
        "    timeframe = '1h'\n"
        "    can_short = True\n",
        encoding="utf-8",
    )
    config = tmp_path / "futures.json"
    config.write_text('{"trading_mode": "futures"}', encoding="utf-8")
    futures_dir = tmp_path / "user_data" / "data" / "binance" / "futures"
    futures_dir.mkdir(parents=True)
    (futures_dir / "BTC_USDT_USDT-1h-mark.feather").write_text("", encoding="utf-8")
    (futures_dir / "BTC_USDT_USDT-1h-funding_rate.feather").write_text("", encoding="utf-8")
    manifest = StrategyManifest(
        strategy_id="strategy_short",
        signal_id="signal_001",
        name="ShortStrategy",
        file_path=str(strategy_file),
        generated_at="2026-05-14T00:00:00",
        timeframe="1h",
        symbols=["BTC/USDT:USDT"],
        assumptions=["short test"],
        failure_modes=["missing data"],
    )

    preflight = build_backtest_preflight(
        manifest=manifest,
        strategy_file=strategy_file,
        config_path=config,
        userdir=tmp_path / "user_data",
        timerange="20240101-20260501",
        pairs=["BTC/USDT:USDT"],
    )

    assert preflight["ok"] is False
    assert preflight["data_checks"][0]["found_path"] is None


def test_parse_freqtrade_result_json_applies_pass_criteria() -> None:
    report = parse_freqtrade_result_json(
        {
            "total_trades": 116,
            "winrate": 54,
            "profit_factor": 1.34,
            "sharpe": 1.42,
            "max_drawdown": -0.09,
            "profit_total": 0.18,
        },
        backtest_id="backtest_001",
        strategy_id="strategy_001",
        timerange="20240101-20260501",
    )

    assert report.status == BacktestStatus.PASSED
    assert report.win_rate == 0.54


def test_parse_nested_freqtrade_result_and_trades() -> None:
    payload = {
        "strategy": {
            "ExampleStrategy": {
                "total_trades": 116,
                "winrate": 54,
                "profit_factor": 1.34,
                "sharpe": 1.42,
                "max_drawdown": 0.09,
                "profit_total": 0.18,
                "trades": [{"trade_id": "t1"}],
            }
        }
    }

    report = parse_freqtrade_result_json(
        payload,
        backtest_id="backtest_001",
        strategy_id="strategy_001",
        timerange="20240101-20260501",
    )
    trades = extract_freqtrade_trades(payload, strategy_name="ExampleStrategy")

    assert report.status == BacktestStatus.PASSED
    assert report.max_drawdown == -0.09
    assert trades == [{"trade_id": "t1"}]


def test_load_freqtrade_zip_result_and_prefer_zip(tmp_path) -> None:
    meta_path = tmp_path / "backtest-result.meta.json"
    meta_path.write_text("{}", encoding="utf-8")
    zip_path = tmp_path / "backtest-result.zip"
    payload = {"strategy": {"ExampleStrategy": {"total_trades": 3}}}
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("backtest-result_config.json", "{}")
        archive.writestr("backtest-result.json", json.dumps(payload))

    assert find_latest_backtest_result(tmp_path) == zip_path
    assert load_freqtrade_result(zip_path) == payload
