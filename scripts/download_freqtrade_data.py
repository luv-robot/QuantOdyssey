import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Freqtrade historical data.")
    parser.add_argument(
        "--pairs",
        default=os.getenv(
            "FREQTRADE_PAIRS",
            "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,DOGE/USDT,XRP/USDT,ADA/USDT",
        ),
    )
    parser.add_argument("--timeframes", default=os.getenv("FREQTRADE_TIMEFRAMES", "5m,15m,1h"))
    parser.add_argument("--exchange", default=os.getenv("FREQTRADE_EXCHANGE", "binance"))
    parser.add_argument("--userdir", default=os.getenv("FREQTRADE_USER_DATA", "freqtrade_user_data"))
    parser.add_argument("--config", default=None)
    parser.add_argument("--days", type=int, default=int(os.getenv("FREQTRADE_DOWNLOAD_DAYS", "1950")))
    parser.add_argument("--trading-mode", default="spot", choices=["spot", "futures"])
    parser.add_argument("--freqtrade-bin", default=os.getenv("FREQTRADE_BIN", "freqtrade"))
    args = parser.parse_args()
    if args.config is None:
        args.config = (
            os.getenv("FREQTRADE_FUTURES_CONFIG", "configs/freqtrade_futures_config.json")
            if args.trading_mode == "futures"
            else os.getenv("FREQTRADE_CONFIG", "configs/freqtrade_config.json")
        )
    pairs = [_normalize_pair(pair.strip(), args.trading_mode) for pair in args.pairs.split(",") if pair.strip()]

    freqtrade_bin = shutil.which(args.freqtrade_bin)
    if freqtrade_bin is None:
        print(f"Freqtrade binary not found: {args.freqtrade_bin}", file=sys.stderr)
        print("Set FREQTRADE_BIN or activate the environment where freqtrade is installed.", file=sys.stderr)
        return 127

    Path(args.userdir).mkdir(parents=True, exist_ok=True)
    command = [
        freqtrade_bin,
        "download-data",
        "--exchange",
        args.exchange,
        "--userdir",
        args.userdir,
        "--config",
        args.config,
        "--pairs",
        *pairs,
        "--timeframes",
        *[timeframe.strip() for timeframe in args.timeframes.split(",") if timeframe.strip()],
        "--days",
        str(args.days),
        "--trading-mode",
        args.trading_mode,
    ]
    print("Running:", " ".join(command))
    return subprocess.run(command, check=False).returncode


def _normalize_pair(pair: str, trading_mode: str) -> str:
    if trading_mode != "futures" or ":" in pair:
        return pair
    return f"{pair}:USDT"


if __name__ == "__main__":
    raise SystemExit(main())
