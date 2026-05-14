import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import StrategyManifest  # noqa: E402
from app.services.backtester import build_backtest_preflight  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Freqtrade backtest data availability.")
    parser.add_argument(
        "--pairs",
        default=os.getenv(
            "FREQTRADE_PAIRS",
            "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,DOGE/USDT,XRP/USDT,ADA/USDT",
        ),
    )
    parser.add_argument("--timeframes", default=os.getenv("FREQTRADE_TIMEFRAMES", "5m,15m,1h"))
    parser.add_argument("--userdir", default=os.getenv("FREQTRADE_USER_DATA", "freqtrade_user_data"))
    parser.add_argument("--spot-config", default=os.getenv("FREQTRADE_CONFIG", "configs/freqtrade_config.json"))
    parser.add_argument(
        "--futures-config",
        default=os.getenv("FREQTRADE_FUTURES_CONFIG", "configs/freqtrade_futures_config.json"),
    )
    args = parser.parse_args()

    pairs = [pair.strip() for pair in args.pairs.split(",") if pair.strip()]
    timeframes = [timeframe.strip() for timeframe in args.timeframes.split(",") if timeframe.strip()]
    reports = []
    for trading_mode, config_path in [
        ("spot", Path(args.spot_config)),
        ("futures", Path(args.futures_config)),
    ]:
        for timeframe in timeframes:
            manifest = StrategyManifest(
                strategy_id=f"env_check_{trading_mode}_{timeframe}",
                signal_id="environment_check",
                name="EnvironmentCheck",
                file_path="environment_check.py",
                generated_at="2026-01-01T00:00:00",
                timeframe=timeframe,
                symbols=[_normalize_pair(pair, trading_mode) for pair in pairs],
                assumptions=["environment check"],
                failure_modes=["missing historical data"],
            )
            reports.append(
                build_backtest_preflight(
                    manifest=manifest,
                    strategy_file=Path(__file__),
                    config_path=config_path,
                    userdir=Path(args.userdir),
                    timerange="20240101-20260501",
                    pairs=manifest.symbols,
                    requires_short=(trading_mode == "futures"),
                )
            )
    print(json.dumps({"reports": reports}, indent=2))
    return 0 if all(report["ok"] for report in reports) else 2


def _normalize_pair(pair: str, trading_mode: str) -> str:
    if trading_mode != "futures" or ":" in pair:
        return pair
    return f"{pair}:USDT"


if __name__ == "__main__":
    raise SystemExit(main())
