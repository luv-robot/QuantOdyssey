import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import StrategyManifest  # noqa: E402
from app.services.backtester import build_backtest_preflight  # noqa: E402
from app.services.market_data import BinanceMarketDataClient  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit useful free market data sources.")
    parser.add_argument("--pairs", default=os.getenv("FREQTRADE_PAIRS", "BTC/USDT,ETH/USDT,SOL/USDT"))
    parser.add_argument("--timeframes", default=os.getenv("FREQTRADE_TIMEFRAMES", "5m,15m,1h"))
    parser.add_argument("--spot-config", default=os.getenv("FREQTRADE_CONFIG", "configs/freqtrade_config.json"))
    parser.add_argument(
        "--futures-config",
        default=os.getenv("FREQTRADE_FUTURES_CONFIG", "configs/freqtrade_futures_config.json"),
    )
    parser.add_argument("--userdir", default=os.getenv("FREQTRADE_USERDIR", "freqtrade_user_data"))
    parser.add_argument("--timerange", default=os.getenv("BACKTEST_TIMERANGE", "20240101-20260501"))
    parser.add_argument("--skip-live", action="store_true")
    args = parser.parse_args()

    pairs = [pair.strip() for pair in args.pairs.split(",") if pair.strip()]
    timeframes = [timeframe.strip() for timeframe in args.timeframes.split(",") if timeframe.strip()]
    report = {
        "local_history": _local_history_report(
            pairs=pairs,
            timeframes=timeframes,
            spot_config=Path(args.spot_config),
            futures_config=Path(args.futures_config),
            userdir=Path(args.userdir),
            timerange=args.timerange,
        ),
        "binance_public": [] if args.skip_live else _binance_public_report(pairs, timeframes),
    }
    print(json.dumps(report, indent=2))
    failed = any(not item["ok"] for item in report["local_history"])
    failed = failed or any(not item["ok"] for item in report["binance_public"])
    raise SystemExit(1 if failed else 0)


def _local_history_report(
    pairs: list[str],
    timeframes: list[str],
    spot_config: Path,
    futures_config: Path,
    userdir: Path,
    timerange: str,
) -> list[dict[str, Any]]:
    reports = []
    for trading_mode, config_path, requires_short in [
        ("spot", spot_config, False),
        ("futures", futures_config, True),
    ]:
        for timeframe in timeframes:
            mode_pairs = [_normalize_pair_for_mode(pair, trading_mode) for pair in pairs]
            manifest = StrategyManifest(
                strategy_id=f"data_audit_{trading_mode}_{timeframe}",
                signal_id="data_audit",
                name="DataAudit",
                file_path=str(Path(__file__).resolve()),
                generated_at="2026-05-14T00:00:00",
                timeframe=timeframe,
                symbols=mode_pairs,
                assumptions=["data audit"],
                failure_modes=["missing data"],
            )
            preflight = build_backtest_preflight(
                manifest=manifest,
                strategy_file=Path(__file__).resolve(),
                config_path=config_path,
                userdir=userdir,
                timerange=timerange,
                pairs=mode_pairs,
                requires_short=requires_short,
            )
            reports.append(
                {
                    "source": f"freqtrade_{trading_mode}_ohlcv",
                    "timeframe": timeframe,
                    "ok": preflight["ok"],
                    "errors": preflight["errors"],
                    "data_checks": preflight["data_checks"],
                }
            )
    return reports


def _binance_public_report(pairs: list[str], timeframes: list[str]) -> list[dict[str, Any]]:
    client = BinanceMarketDataClient()
    checks: list[dict[str, Any]] = []
    first_timeframe = timeframes[0] if timeframes else "5m"
    for pair in pairs:
        checks.extend(
            [
                _endpoint_check(
                    "binance_spot_ohlcv",
                    pair,
                    lambda pair=pair: client.fetch_ohlcv(pair, interval=first_timeframe, limit=5, trading_mode="spot"),
                ),
                _endpoint_check(
                    "binance_futures_ohlcv",
                    pair,
                    lambda pair=pair: client.fetch_ohlcv(pair, interval=first_timeframe, limit=5, trading_mode="futures"),
                ),
                _endpoint_check(
                    "binance_funding_rate",
                    pair,
                    lambda pair=pair: client.fetch_funding_rate(pair, limit=5),
                ),
                _endpoint_check(
                    "binance_open_interest_current",
                    pair,
                    lambda pair=pair: client.fetch_open_interest(pair),
                ),
                _endpoint_check(
                    "binance_open_interest_history",
                    pair,
                    lambda pair=pair: client.fetch_open_interest_history(pair, period=first_timeframe, limit=5),
                ),
                _endpoint_check(
                    "binance_spot_orderbook",
                    pair,
                    lambda pair=pair: client.fetch_orderbook(pair, limit=20, trading_mode="spot"),
                ),
                _endpoint_check(
                    "binance_futures_orderbook",
                    pair,
                    lambda pair=pair: client.fetch_orderbook(pair, limit=20, trading_mode="futures"),
                ),
            ]
        )
    return checks


def _endpoint_check(name: str, pair: str, fetch: Callable[[], Any]) -> dict[str, Any]:
    try:
        payload = fetch()
    except Exception as exc:  # pragma: no cover - exercised against real networks.
        return {"source": name, "pair": pair, "ok": False, "error": str(exc)}
    count = len(payload) if isinstance(payload, list) else 1
    return {"source": name, "pair": pair, "ok": count > 0, "records": count}


def _normalize_pair_for_mode(pair: str, trading_mode: str) -> str:
    base = pair.split(":", 1)[0]
    if trading_mode == "futures":
        return pair if ":" in pair else f"{base}:USDT"
    return base


if __name__ == "__main__":
    main()
