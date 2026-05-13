from __future__ import annotations

import json
import re
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.models import BacktestReport, BacktestStatus, StrategyManifest, TradeRecord
from app.services.reviewer import parse_freqtrade_trades


def parse_strategy_name(strategy_file: Path) -> str:
    code = strategy_file.read_text(encoding="utf-8")
    match = re.search(r"class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", code)
    if match is None:
        raise ValueError(f"Could not find strategy class in {strategy_file}")
    return match.group(1)


def build_backtest_command(
    strategy_name: str,
    timerange: str,
    config_path: Path = Path("configs/freqtrade_config.json"),
    userdir: Path = Path("freqtrade_user_data"),
    export_filename: Path | None = None,
    backtest_directory: Path | None = None,
    pairs: list[str] | None = None,
) -> list[str]:
    command = [
        "freqtrade",
        "backtesting",
        "--strategy",
        strategy_name,
        "--config",
        str(config_path),
        "--userdir",
        str(userdir),
        "--timerange",
        timerange,
        "--export",
        "trades",
    ]
    if pairs:
        command.extend(["--pairs", *pairs])
    if backtest_directory is not None:
        command.extend(["--backtest-directory", str(backtest_directory)])
    elif export_filename is not None:
        command.extend(["--export-filename", str(export_filename)])
    return command


def parse_freqtrade_result_json(
    payload: dict[str, Any],
    backtest_id: str,
    strategy_id: str,
    timerange: str,
) -> BacktestReport:
    metrics = _extract_strategy_metrics(payload)
    trades = int(metrics.get("total_trades", metrics.get("trades", 0)))
    profit_factor = float(metrics.get("profit_factor", 0))
    max_drawdown = _normalize_drawdown(metrics.get("max_drawdown", metrics.get("max_drawdown_account", 0)))
    total_return = float(metrics.get("profit_total", metrics.get("total_return", 0)))
    win_rate = float(metrics.get("winrate", metrics.get("win_rate", 0)))
    if win_rate > 1:
        win_rate = win_rate / 100

    status = (
        BacktestStatus.PASSED
        if profit_factor >= 1.2 and max_drawdown >= -0.15 and trades >= 50
        else BacktestStatus.FAILED
    )
    return BacktestReport(
        backtest_id=backtest_id,
        strategy_id=strategy_id,
        timerange=timerange,
        trades=trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        sharpe=metrics.get("sharpe"),
        max_drawdown=max_drawdown,
        total_return=total_return,
        status=status,
        error=None if status == BacktestStatus.PASSED else "Freqtrade result did not meet pass criteria.",
    )


def run_freqtrade_backtest(
    manifest: StrategyManifest,
    timerange: str = "20240101-20260501",
    config_path: Path = Path("configs/freqtrade_config.json"),
    userdir: Path = Path("freqtrade_user_data"),
    timeout_seconds: int = 600,
    pairs: list[str] | None = None,
    backtest_id_suffix: str | None = None,
) -> tuple[BacktestReport, list[TradeRecord], dict[str, Any]]:
    strategy_file = Path(manifest.file_path)
    if not strategy_file.is_absolute():
        strategy_file = Path.cwd() / strategy_file
    strategy_name = parse_strategy_name(strategy_file)
    export_dir = userdir / "backtest_results"
    export_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.utcnow().timestamp()
    export_filename = export_dir / f"{manifest.strategy_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"
    command = build_backtest_command(
        strategy_name=strategy_name,
        timerange=timerange,
        config_path=config_path,
        userdir=userdir,
        backtest_directory=export_dir,
        pairs=pairs,
    )
    completed = run_freqtrade_command(command, timeout_seconds=timeout_seconds)
    metadata = {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "export_filename": str(export_filename),
    }
    suffix = "" if backtest_id_suffix is None else f"_{backtest_id_suffix}"
    backtest_id = f"backtest_{manifest.strategy_id}{suffix}"
    if completed.returncode != 0:
        return (
            _failed_backtest(
                backtest_id,
                manifest.strategy_id,
                timerange,
                f"Freqtrade exited with code {completed.returncode}.",
            ),
            [],
            metadata,
        )

    result_path = export_filename if export_filename.exists() else find_latest_backtest_result(export_dir, since=started_at)
    if result_path is None:
        return (
            _failed_backtest(
                backtest_id,
                manifest.strategy_id,
                timerange,
                "Freqtrade completed but no backtest result was found.",
            ),
            [],
            metadata,
        )
    payload = load_freqtrade_result(result_path)
    metadata["result_path"] = str(result_path)
    report = parse_freqtrade_result_json(payload, backtest_id, manifest.strategy_id, timerange)
    trade_payload = extract_freqtrade_trades(payload, strategy_name=strategy_name)
    trade_symbol = (pairs or manifest.symbols)[0]
    trades = parse_freqtrade_trades(manifest.strategy_id, trade_symbol, trade_payload)
    return report, trades, metadata


def find_latest_backtest_result(export_dir: Path, since: float | None = None) -> Path | None:
    candidates = [
        path
        for pattern in ("*.zip", "*.json")
        for path in export_dir.glob(pattern)
        if "last_result" not in path.name and "meta" not in path.name and path.is_file()
    ]
    if since is not None:
        candidates = [path for path in candidates if path.stat().st_mtime >= since]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def extract_freqtrade_trades(payload: dict[str, Any], strategy_name: str | None = None) -> list[dict[str, Any]]:
    metrics = _extract_strategy_metrics(payload, strategy_name=strategy_name)
    trades = metrics.get("trades", payload.get("trades", []))
    if isinstance(trades, list):
        return [trade for trade in trades if isinstance(trade, dict)]
    return []


def run_freqtrade_command(command: list[str], timeout_seconds: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)


def load_freqtrade_result(path: Path) -> dict[str, Any]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            result_names = [
                name
                for name in archive.namelist()
                if name.endswith(".json") and not name.endswith("_config.json") and not name.endswith(".meta.json")
            ]
            if not result_names:
                raise ValueError(f"No result JSON found in {path}")
            return json.loads(archive.read(result_names[0]).decode("utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_strategy_metrics(
    payload: dict[str, Any],
    strategy_name: str | None = None,
) -> dict[str, Any]:
    strategy = payload.get("strategy")
    if isinstance(strategy, dict):
        if strategy_name and isinstance(strategy.get(strategy_name), dict):
            return strategy[strategy_name]
        if "total_trades" in strategy or "trades" in strategy:
            return strategy
        for value in strategy.values():
            if isinstance(value, dict):
                return value
    return payload


def _normalize_drawdown(value: Any) -> float:
    drawdown = float(value or 0)
    if drawdown > 0:
        return -drawdown
    return drawdown


def _failed_backtest(
    backtest_id: str,
    strategy_id: str,
    timerange: str,
    error: str,
) -> BacktestReport:
    return BacktestReport(
        backtest_id=backtest_id,
        strategy_id=strategy_id,
        timerange=timerange,
        trades=0,
        win_rate=0,
        profit_factor=0,
        sharpe=None,
        max_drawdown=0,
        total_return=0,
        status=BacktestStatus.FAILED,
        error=error,
    )
