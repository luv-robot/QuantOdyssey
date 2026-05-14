from __future__ import annotations

import json
import os
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


def strategy_allows_short(strategy_file: Path) -> bool:
    code = strategy_file.read_text(encoding="utf-8")
    return re.search(r"^\s*can_short\s*=\s*True\b", code, flags=re.MULTILINE) is not None


def load_freqtrade_trading_mode(config_path: Path) -> str:
    if not config_path.exists():
        return "missing"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    mode = str(payload.get("trading_mode") or "spot").lower()
    return mode if mode in {"spot", "futures"} else "spot"


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
    futures_config_path: Path | None = None,
    userdir: Path = Path("freqtrade_user_data"),
    timeout_seconds: int = 600,
    pairs: list[str] | None = None,
    backtest_id_suffix: str | None = None,
) -> tuple[BacktestReport, list[TradeRecord], dict[str, Any]]:
    strategy_file = Path(manifest.file_path)
    if not strategy_file.is_absolute():
        strategy_file = Path.cwd() / strategy_file
    strategy_name = parse_strategy_name(strategy_file)
    requires_short = strategy_allows_short(strategy_file)
    selected_config_path = _select_config_path(
        config_path,
        futures_config_path or Path(os.getenv("FREQTRADE_FUTURES_CONFIG", "configs/freqtrade_futures_config.json")),
        requires_short=requires_short,
    )
    trading_mode = load_freqtrade_trading_mode(selected_config_path)
    command_pairs = _normalize_pairs_for_trading_mode(pairs or manifest.symbols, trading_mode)
    preflight = build_backtest_preflight(
        manifest=manifest,
        strategy_file=strategy_file,
        config_path=selected_config_path,
        userdir=userdir,
        timerange=timerange,
        pairs=command_pairs,
        requires_short=requires_short,
    )
    export_dir = userdir / "backtest_results"
    export_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.utcnow().timestamp()
    export_filename = export_dir / f"{manifest.strategy_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"
    suffix = "" if backtest_id_suffix is None else f"_{backtest_id_suffix}"
    backtest_id = f"backtest_{manifest.strategy_id}{suffix}"
    if not preflight["ok"]:
        return (
            _failed_backtest(
                backtest_id,
                manifest.strategy_id,
                timerange,
                "Backtest preflight failed: " + "; ".join(preflight["errors"]),
            ),
            [],
            {
                "command": [],
                "returncode": None,
                "stdout_tail": "",
                "stderr_tail": "",
                "export_filename": str(export_filename),
                "config_path": str(selected_config_path),
                "preflight": preflight,
                "trading_mode": trading_mode,
            },
        )
    command = build_backtest_command(
        strategy_name=strategy_name,
        timerange=timerange,
        config_path=selected_config_path,
        userdir=userdir,
        backtest_directory=export_dir,
        pairs=command_pairs,
    )
    completed = run_freqtrade_command(command, timeout_seconds=timeout_seconds)
    metadata = {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "export_filename": str(export_filename),
        "config_path": str(selected_config_path),
        "preflight": preflight,
        "trading_mode": trading_mode,
    }
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
    trade_symbol = command_pairs[0]
    trades = parse_freqtrade_trades(manifest.strategy_id, trade_symbol, trade_payload)
    return report, trades, metadata


def build_backtest_preflight(
    manifest: StrategyManifest,
    strategy_file: Path,
    config_path: Path,
    userdir: Path,
    timerange: str,
    pairs: list[str],
    requires_short: bool | None = None,
) -> dict[str, Any]:
    requires_short = strategy_allows_short(strategy_file) if requires_short is None else requires_short
    trading_mode = load_freqtrade_trading_mode(config_path)
    errors: list[str] = []
    warnings: list[str] = []
    if not config_path.exists():
        errors.append(f"config file is missing: {config_path}")
    if requires_short and trading_mode != "futures":
        errors.append("strategy has can_short=True but selected config is not futures")
    if not pairs:
        errors.append("no pairs configured for backtest")

    data_checks = [
        _data_file_check(userdir, pair, manifest.timeframe, trading_mode)
        for pair in pairs
    ]
    missing = [item for item in data_checks if item["found_path"] is None]
    if missing:
        missing_pairs = ", ".join(f"{item['pair']} {manifest.timeframe}" for item in missing)
        errors.append(f"missing {trading_mode} OHLCV data for {missing_pairs}")
        warnings.append(
            "Run scripts/download_freqtrade_data.py with the same trading mode, pair list, "
            "timeframes, and config before trusting real backtests."
        )
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "strategy_file": str(strategy_file),
        "config_path": str(config_path),
        "trading_mode": trading_mode,
        "requires_short": requires_short,
        "timerange": timerange,
        "pairs": pairs,
        "timeframe": manifest.timeframe,
        "data_checks": data_checks,
    }


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


def _select_config_path(
    spot_config_path: Path,
    futures_config_path: Path,
    requires_short: bool,
) -> Path:
    if requires_short:
        return futures_config_path
    return spot_config_path


def _normalize_pairs_for_trading_mode(pairs: list[str], trading_mode: str) -> list[str]:
    if trading_mode != "futures":
        return [_strip_futures_settlement(pair) for pair in pairs]
    normalized = []
    for pair in pairs:
        base_pair = _strip_futures_settlement(pair)
        normalized.append(pair if ":" in pair else f"{base_pair}:USDT")
    return normalized


def _strip_futures_settlement(pair: str) -> str:
    return pair.split(":", 1)[0]


def _data_file_check(userdir: Path, pair: str, timeframe: str, trading_mode: str) -> dict[str, Any]:
    data_root = userdir / "data"
    candidates = _data_file_candidates(data_root, pair, timeframe, trading_mode)
    found = next((path for path in candidates if path.exists()), None)
    if found is None and data_root.exists():
        tokens = _pair_file_tokens(pair)
        matches = [
            path
            for path in data_root.rglob(f"*{timeframe}*")
            if path.is_file()
            and path.suffix in {".feather", ".json", ".json.gz"}
            and all(token in path.name for token in tokens[:2])
        ]
        found = matches[0] if matches else None
    return {
        "pair": pair,
        "timeframe": timeframe,
        "trading_mode": trading_mode,
        "expected_paths": [str(path) for path in candidates],
        "found_path": None if found is None else str(found),
    }


def _data_file_candidates(
    data_root: Path,
    pair: str,
    timeframe: str,
    trading_mode: str,
) -> list[Path]:
    base_pair = _strip_futures_settlement(pair)
    spot_name = base_pair.replace("/", "_")
    futures_name = pair.replace("/", "_").replace(":", "_")
    names = [f"{spot_name}-{timeframe}.feather", f"{spot_name}-{timeframe}.json"]
    if trading_mode == "futures":
        names = [
            f"{futures_name}-{timeframe}.feather",
            f"{futures_name}-{timeframe}.json",
            f"{spot_name}-{timeframe}-futures.feather",
            *names,
        ]
    return [data_root / "binance" / name for name in names]


def _pair_file_tokens(pair: str) -> list[str]:
    return [token for token in re.split(r"[/_:.-]+", pair) if token]


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
