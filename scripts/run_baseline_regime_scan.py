import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.harness import build_baseline_implied_regime_report, build_strategy_family_baseline_board  # noqa: E402
from app.services.market_data import load_freqtrade_ohlcv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build generic baseline board and infer a provisional baseline-implied regime."
    )
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--timeframe", action="append", default=[])
    parser.add_argument("--data-dir", default="freqtrade_user_data/data/binance/futures")
    parser.add_argument("--max-candles", type=int, default=20000)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    candles_by_cell = _load_candles(args)
    board = build_strategy_family_baseline_board(candles_by_cell)
    regime = build_baseline_implied_regime_report(board)
    print(
        json.dumps(
            {
                "baseline_board": board.model_dump(mode="json"),
                "baseline_implied_regime": regime.model_dump(mode="json"),
            },
            indent=2,
        )
    )
    return 0


def _load_candles(args: argparse.Namespace):
    data_dir = Path(args.data_dir)
    symbols = args.symbol or ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    timeframes = args.timeframe or ["1h"]
    candles_by_cell = {}
    for symbol in symbols:
        for timeframe in timeframes:
            path = data_dir / f"{_freqtrade_symbol(symbol)}-{timeframe}-futures.feather"
            if not path.exists():
                continue
            candles = load_freqtrade_ohlcv(path, symbol, timeframe)
            if args.max_candles > 0 and len(candles) > args.max_candles:
                candles = candles[-args.max_candles :]
            candles_by_cell[(symbol, timeframe)] = candles
    if not candles_by_cell:
        raise SystemExit(f"No OHLCV files found under {data_dir}.")
    return candles_by_cell


def _freqtrade_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


if __name__ == "__main__":
    raise SystemExit(main())
