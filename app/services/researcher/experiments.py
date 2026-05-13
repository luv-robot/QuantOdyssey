from __future__ import annotations

import hashlib
import json
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from app.models import BacktestReport, ExperimentManifest, MarketSignal, StrategyManifest


def build_experiment_manifest(
    signal: MarketSignal,
    manifest: StrategyManifest,
    backtest: BacktestReport,
    strategy_code: str,
    backtest_mode: str,
    metadata: dict[str, Any] | None = None,
    config_path: Path | None = None,
    random_seed: int | None = None,
) -> ExperimentManifest:
    backtest_metadata = metadata or {}
    return ExperimentManifest(
        experiment_id=f"experiment_{backtest.backtest_id}",
        thesis_id=manifest.thesis_id,
        signal_id=signal.signal_id,
        strategy_id=manifest.strategy_id,
        backtest_id=backtest.backtest_id,
        backtest_mode=backtest_mode,
        timerange=backtest.timerange,
        strategy_code_hash=_hash_text(strategy_code),
        config_hash=_hash_file(config_path) if config_path is not None else None,
        data_fingerprint=_hash_json(
            {
                "exchange": signal.exchange,
                "symbol": signal.symbol,
                "timeframe": signal.timeframe,
                "data_sources": signal.data_sources,
                "features": signal.features,
                "timerange": backtest.timerange,
            }
        ),
        freqtrade_version=backtest_metadata.get("freqtrade_version") or _freqtrade_version(),
        command=[str(item) for item in backtest_metadata.get("command", [])],
        result_path=backtest_metadata.get("result_path"),
        fee_model=backtest_metadata.get("fee_model", {}),
        slippage_model=backtest_metadata.get("slippage_model", {}),
        random_seed=random_seed,
        metadata={
            key: value
            for key, value in backtest_metadata.items()
            if key
            not in {
                "command",
                "result_path",
                "fee_model",
                "slippage_model",
                "freqtrade_version",
            }
        },
    )


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_json(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return _hash_text(payload)


def _freqtrade_version() -> str | None:
    try:
        return importlib_metadata.version("freqtrade")
    except importlib_metadata.PackageNotFoundError:
        return None
