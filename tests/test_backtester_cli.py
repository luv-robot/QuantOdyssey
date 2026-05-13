from pathlib import Path
import json
import zipfile

from app.models import BacktestStatus
from app.services.backtester import (
    build_backtest_command,
    extract_freqtrade_trades,
    find_latest_backtest_result,
    load_freqtrade_result,
    parse_freqtrade_result_json,
    parse_strategy_name,
)


def test_parse_strategy_name_from_freqtrade_file(tmp_path) -> None:
    strategy_file = tmp_path / "ExampleStrategy.py"
    strategy_file.write_text(
        "from freqtrade.strategy import IStrategy\n\nclass ExampleStrategy(IStrategy):\n    pass\n",
        encoding="utf-8",
    )

    assert parse_strategy_name(strategy_file) == "ExampleStrategy"


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
