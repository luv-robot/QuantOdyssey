import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.market_data import BinanceMarketDataClient, build_orderflow_bars  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Binance aggTrades and build orderflow bars.")
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--trading-mode", choices=["futures", "spot"], default="futures")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--lookback-minutes", type=int, default=240)
    parser.add_argument("--start-time")
    parser.add_argument("--end-time")
    parser.add_argument("--bar-interval", default="1m")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--dataset-prefix")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    end_time = _parse_time(args.end_time) if args.end_time else datetime.utcnow()
    start_time = (
        _parse_time(args.start_time)
        if args.start_time
        else end_time - timedelta(minutes=args.lookback_minutes)
    )
    client = BinanceMarketDataClient()
    trades = client.fetch_aggregate_trades(
        args.symbol,
        limit=args.limit,
        trading_mode=args.trading_mode,
        start_time=start_time,
        end_time=end_time,
    )
    bars = build_orderflow_bars(trades, interval=args.bar_interval)
    dataset_prefix = args.dataset_prefix or (
        f"binance:{args.trading_mode}:agg_trades:{_safe_symbol(args.symbol)}:"
        f"{start_time.strftime('%Y%m%d%H%M%S')}-{end_time.strftime('%Y%m%d%H%M%S')}"
    )
    if args.save:
        repository = QuantRepository(args.database_url)
        repository.save_aggregate_trades(f"{dataset_prefix}:raw", args.symbol, trades)
        repository.save_orderflow_bars(f"{dataset_prefix}:orderflow:{args.bar_interval}", args.symbol, bars)

    print(
        json.dumps(
            {
                "symbol": args.symbol,
                "trading_mode": args.trading_mode,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "trade_count": len(trades),
                "bar_count": len(bars),
                "raw_dataset_id": f"{dataset_prefix}:raw",
                "orderflow_dataset_id": f"{dataset_prefix}:orderflow:{args.bar_interval}",
                "first_trade_time": None if not trades else trades[0].timestamp.isoformat(),
                "last_trade_time": None if not trades else trades[-1].timestamp.isoformat(),
            },
            indent=2,
        )
    )
    return 0 if trades else 2


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_").lower()


if __name__ == "__main__":
    raise SystemExit(main())
