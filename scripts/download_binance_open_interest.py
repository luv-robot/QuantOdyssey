import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.market_data import BinanceMarketDataClient  # noqa: E402


PERIOD_SECONDS = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "2h": 2 * 60 * 60,
    "4h": 4 * 60 * 60,
    "6h": 6 * 60 * 60,
    "12h": 12 * 60 * 60,
    "1d": 24 * 60 * 60,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Binance futures historical open interest.")
    parser.add_argument("--symbol", default=os.getenv("FREQTRADE_PAIRS", "BTC/USDT:USDT").split(",")[0])
    parser.add_argument("--period", default="5m", choices=sorted(PERIOD_SECONDS))
    parser.add_argument("--days", type=int, default=int(os.getenv("BINANCE_OI_DOWNLOAD_DAYS", "365")))
    parser.add_argument("--output", default=None)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    symbol = _normalize_futures_symbol(args.symbol)
    output = Path(args.output) if args.output else _default_output_path(symbol, args.period)
    output.parent.mkdir(parents=True, exist_ok=True)
    points = download_open_interest(symbol, period=args.period, days=args.days, limit=args.limit)
    output.write_text(json.dumps([point.model_dump(mode="json") for point in points], indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "symbol": symbol,
                "period": args.period,
                "points": len(points),
                "output": str(output),
            },
            indent=2,
        )
    )
    return 0 if points else 2


def download_open_interest(
    symbol: str,
    *,
    period: str,
    days: int,
    limit: int = 500,
    client: BinanceMarketDataClient | None = None,
):
    client = client or BinanceMarketDataClient()
    end = datetime.utcnow()
    cursor = end - timedelta(days=days)
    step = timedelta(seconds=PERIOD_SECONDS[period] * max(1, limit - 1))
    points = []
    seen_timestamps = set()
    while cursor < end:
        window_end = min(end, cursor + step)
        batch = client.fetch_open_interest_history(
            symbol,
            period=period,
            limit=limit,
            start_time=cursor,
            end_time=window_end,
        )
        for point in batch:
            if point.timestamp not in seen_timestamps:
                points.append(point)
                seen_timestamps.add(point.timestamp)
        cursor = window_end + timedelta(seconds=PERIOD_SECONDS[period])
    return sorted(points, key=lambda item: item.timestamp)


def _normalize_futures_symbol(symbol: str) -> str:
    if ":" in symbol:
        return symbol
    return f"{symbol}:USDT"


def _default_output_path(symbol: str, period: str) -> Path:
    name = symbol.replace("/", "_").replace(":", "_")
    return Path("freqtrade_user_data") / "data" / "binance" / "futures" / f"{name}-{period}-open_interest.json"


if __name__ == "__main__":
    raise SystemExit(main())
