import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import FundingRatePoint, OhlcvCandle  # noqa: E402
from app.services.market_data import (  # noqa: E402
    BinanceMarketDataClient,
    build_market_signal_from_dataset,
    clean_ohlcv,
    quality_check_market_dataset,
)
from app.storage import QuantRepository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Freqtrade OHLCV data into QuantOdyssey storage."
    )
    parser.add_argument("--data-file", required=True)
    parser.add_argument("--symbol", default=os.getenv("FREQTRADE_PAIRS", "BTC/USDT").split(",")[0])
    parser.add_argument("--interval", default=os.getenv("FREQTRADE_TIMEFRAMES", "5m").split(",")[0])
    parser.add_argument("--exchange", default=os.getenv("FREQTRADE_EXCHANGE", "binance"))
    parser.add_argument("--min-rank", type=int, default=70)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    parser.add_argument("--skip-live-aux", action="store_true")
    parser.add_argument("--funding-file", default=None)
    args = parser.parse_args()

    candles = load_freqtrade_ohlcv(Path(args.data_file), args.symbol, args.interval)
    cleaned = clean_ohlcv(candles)
    dataset_prefix = f"freqtrade:{args.exchange}:{args.symbol}:{args.interval}"

    client = BinanceMarketDataClient()
    funding_rates = []
    open_interest = None
    orderbook = None
    if args.funding_file:
        funding_rates = load_freqtrade_funding_rates(Path(args.funding_file), args.symbol)
    if not args.skip_live_aux:
        if not funding_rates:
            funding_rates = client.fetch_funding_rate(args.symbol)
        open_interest = client.fetch_open_interest(args.symbol)
        orderbook = client.fetch_orderbook(args.symbol)

    quality = quality_check_market_dataset(
        dataset_prefix,
        cleaned,
        orderbook=orderbook,
        funding_rates=funding_rates if args.funding_file else None,
        open_interest_points=[open_interest] if open_interest is not None else None,
    )
    repository = QuantRepository(args.database_url)
    repository.save_ohlcv(f"{dataset_prefix}:ohlcv", args.symbol, cleaned)
    repository.save_data_quality_report(quality)
    if funding_rates:
        repository.save_funding_rates(f"{dataset_prefix}:funding", args.symbol, funding_rates)
    if open_interest is not None:
        repository.save_open_interest(f"{dataset_prefix}:open_interest", args.symbol, open_interest)
    if orderbook is not None:
        repository.save_orderbook(f"{dataset_prefix}:orderbook", args.symbol, orderbook)

    signal = None
    if quality.is_usable and open_interest is not None and orderbook is not None:
        signal = build_market_signal_from_dataset(
            symbol=args.symbol,
            candles=cleaned,
            funding_rates=funding_rates,
            open_interest=open_interest,
            orderbook=orderbook,
            min_rank=args.min_rank,
        )
        if signal is not None:
            signal = signal.model_copy(
                update={
                    "data_sources": [
                        f"{dataset_prefix}:ohlcv",
                        f"{dataset_prefix}:funding",
                        f"{dataset_prefix}:open_interest",
                        f"{dataset_prefix}:orderbook",
                    ]
                }
            )
            repository.save_signal(signal)

    print(
        json.dumps(
            {
                "dataset_prefix": dataset_prefix,
                "imported_candles": len(cleaned),
                "dropped_candles": len(candles) - len(cleaned),
                "quality_report": quality.model_dump(mode="json"),
                "signal": None if signal is None else signal.model_dump(mode="json"),
            },
            indent=2,
        )
    )


def load_freqtrade_ohlcv(path: Path, symbol: str, interval: str) -> list[OhlcvCandle]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("pandas is required to import Freqtrade feather data.") from exc

    frame = pd.read_feather(path)
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise SystemExit(f"Freqtrade data file is missing columns: {sorted(missing)}")
    return [_row_to_candle(row, symbol, interval) for row in frame.to_dict("records")]


def load_freqtrade_funding_rates(path: Path, symbol: str) -> list[FundingRatePoint]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("pandas is required to import Freqtrade feather data.") from exc

    frame = pd.read_feather(path)
    required = {"date", "open"}
    missing = required.difference(frame.columns)
    if missing:
        raise SystemExit(f"Freqtrade funding file is missing columns: {sorted(missing)}")
    return [_row_to_funding_rate(row, symbol) for row in frame.to_dict("records")]


def _row_to_candle(row: dict[str, Any], symbol: str, interval: str) -> OhlcvCandle:
    open_time = row["date"].to_pydatetime()
    close_time = open_time + _interval_delta(interval)
    quote_volume = float(row.get("quote_volume") or row["close"] * row["volume"])
    trade_count = int(row.get("trade_count") or 0)
    raw = [
        int(open_time.timestamp() * 1000),
        str(row["open"]),
        str(row["high"]),
        str(row["low"]),
        str(row["close"]),
        str(row["volume"]),
        int(close_time.timestamp() * 1000),
        str(quote_volume),
        trade_count,
    ]
    return OhlcvCandle(
        symbol=symbol.upper(),
        interval=interval,
        open_time=open_time,
        close_time=close_time,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        quote_volume=quote_volume,
        trade_count=trade_count,
        raw=raw,
    )


def _row_to_funding_rate(row: dict[str, Any], symbol: str) -> FundingRatePoint:
    funding_time = row["date"].to_pydatetime()
    return FundingRatePoint(
        symbol=symbol.upper(),
        funding_time=funding_time,
        funding_rate=float(row["open"]),
        mark_price=None,
        raw={
            "date": funding_time.isoformat(),
            "fundingRate": float(row["open"]),
            "source": "freqtrade_funding_rate_feather",
        },
    )


def _interval_delta(interval: str) -> timedelta:
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    raise ValueError(f"Unsupported interval: {interval}")


if __name__ == "__main__":
    main()
