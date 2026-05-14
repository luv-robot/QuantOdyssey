import argparse
import csv
import io
import json
import os
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import AggregateTrade, OrderflowBar  # noqa: E402
from app.services.market_data import build_orderflow_bars  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


BASE_URL = "https://data.binance.vision/data"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Binance public aggTrades archives into orderflow bars.")
    parser.add_argument("--symbols", default=os.getenv("ORDERFLOW_BACKFILL_SYMBOLS", "BTC/USDT:USDT"))
    parser.add_argument("--trading-mode", choices=["futures", "spot"], default="futures")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--bar-interval", default="1m")
    parser.add_argument("--save-raw", action="store_true")
    parser.add_argument("--fail-on-missing", action="store_true")
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--max-rows-per-file", type=int, default=0)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    repository = QuantRepository(args.database_url)
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    days = list(_date_range(_parse_date(args.start_date), _parse_date(args.end_date)))
    processed_files = 0
    results = []
    for symbol in symbols:
        cvd = 0.0
        for day in days:
            if args.max_files and processed_files >= args.max_files:
                break
            url = _archive_url(symbol, day, args.trading_mode)
            try:
                if args.save_raw:
                    trades = list(_iter_archive_trades(symbol, url, max_rows=args.max_rows_per_file))
                    bars = build_orderflow_bars(trades, interval=args.bar_interval, start_cvd=cvd)
                    trade_count = len(trades)
                else:
                    trades = []
                    bars, trade_count = _download_archive_orderflow_bars(
                        symbol,
                        url,
                        interval=args.bar_interval,
                        start_cvd=cvd,
                        max_rows=args.max_rows_per_file,
                    )
            except HTTPError as exc:
                if exc.code == 404 and not args.fail_on_missing:
                    results.append({"symbol": symbol, "date": day.isoformat(), "status": "missing", "url": url})
                    continue
                raise
            if bars:
                cvd = bars[-1].cumulative_volume_delta
            dataset_prefix = (
                f"binance:{args.trading_mode}:archive_agg_trades:{_safe_symbol(symbol)}:"
                f"{day.strftime('%Y%m%d')}"
            )
            if args.save_raw:
                repository.save_aggregate_trades(f"{dataset_prefix}:raw", symbol, trades)
            repository.save_orderflow_bars(f"{dataset_prefix}:orderflow:{args.bar_interval}", symbol, bars)
            results.append(
                {
                    "symbol": symbol,
                    "date": day.isoformat(),
                    "status": "saved",
                    "trade_count": trade_count,
                    "bar_count": len(bars),
                    "orderflow_dataset_id": f"{dataset_prefix}:orderflow:{args.bar_interval}",
                    "raw_dataset_id": f"{dataset_prefix}:raw" if args.save_raw else None,
                    "url": url,
                }
            )
            processed_files += 1
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)
    print(json.dumps({"processed_files": processed_files, "results": results}, indent=2))
    return 0


def _archive_url(symbol: str, day: date, trading_mode: str) -> str:
    market_path = "futures/um" if trading_mode == "futures" else "spot"
    api_symbol = _api_symbol(symbol)
    return f"{BASE_URL}/{market_path}/daily/aggTrades/{api_symbol}/{api_symbol}-aggTrades-{day.isoformat()}.zip"


def _download_archive_orderflow_bars(
    symbol: str,
    url: str,
    *,
    interval: str,
    start_cvd: float = 0.0,
    max_rows: int = 0,
) -> tuple[list[OrderflowBar], int]:
    seconds = _interval_seconds(interval)
    buckets: dict[datetime, dict[str, float | int]] = {}
    trade_count = 0
    for trade in _iter_archive_trades(symbol, url, max_rows=max_rows):
        trade_count += 1
        bucket = _floor_time(trade.timestamp, seconds)
        metrics = buckets.setdefault(
            bucket,
            {
                "buy_volume": 0.0,
                "sell_volume": 0.0,
                "buy_quote": 0.0,
                "sell_quote": 0.0,
                "trade_count": 0,
            },
        )
        quote = trade.quantity * trade.price
        if trade.buyer_is_maker:
            metrics["sell_volume"] += trade.quantity
            metrics["sell_quote"] += quote
        else:
            metrics["buy_volume"] += trade.quantity
            metrics["buy_quote"] += quote
        metrics["trade_count"] += max(1, trade.last_trade_id - trade.first_trade_id + 1)

    cvd = start_cvd
    bars = []
    for open_time in sorted(buckets):
        metrics = buckets[open_time]
        buy_volume = float(metrics["buy_volume"])
        sell_volume = float(metrics["sell_volume"])
        buy_quote = float(metrics["buy_quote"])
        sell_quote = float(metrics["sell_quote"])
        net_volume = buy_volume - sell_volume
        net_quote = buy_quote - sell_quote
        total_volume = buy_volume + sell_volume
        total_quote = buy_quote + sell_quote
        cvd += net_volume
        bars.append(
            OrderflowBar(
                symbol=symbol.upper(),
                interval=interval,
                open_time=open_time,
                close_time=open_time + timedelta(seconds=seconds),
                buy_volume=round(buy_volume, 8),
                sell_volume=round(sell_volume, 8),
                buy_quote_volume=round(buy_quote, 8),
                sell_quote_volume=round(sell_quote, 8),
                net_taker_volume=round(net_volume, 8),
                net_taker_quote_volume=round(net_quote, 8),
                cumulative_volume_delta=round(cvd, 8),
                taker_buy_ratio=round(buy_volume / total_volume, 8) if total_volume else 0.0,
                trade_count=int(metrics["trade_count"]),
                vwap=round(total_quote / total_volume, 8) if total_volume else None,
            )
        )
    return bars, trade_count


def _iter_archive_trades(symbol: str, url: str, *, max_rows: int = 0):
    with urlopen(url, timeout=60) as response:
        blob = response.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        csv_name = next(name for name in archive.namelist() if name.endswith(".csv"))
        with archive.open(csv_name) as file:
            text = io.TextIOWrapper(file)
            rows = csv.reader(text)
            first = next(rows)
            header = first if _looks_like_header(first) else None
            data_rows = rows if header else _prepend(first, rows)
            for index, row in enumerate(data_rows):
                if max_rows and index >= max_rows:
                    break
                if not row:
                    continue
                yield _row_to_trade(symbol, row, header)


def _row_to_trade(symbol: str, row: list[str], header: list[str] | None) -> AggregateTrade:
    if header is None:
        return AggregateTrade(
            symbol=symbol.upper(),
            aggregate_trade_id=int(row[0]),
            price=float(row[1]),
            quantity=float(row[2]),
            first_trade_id=int(row[3]),
            last_trade_id=int(row[4]),
            timestamp=_dt_from_ms(row[5]),
            buyer_is_maker=_bool(row[6]),
            raw={"row": row},
        )

    values = {key.strip().lower(): value for key, value in zip(header, row)}
    return AggregateTrade(
        symbol=symbol.upper(),
        aggregate_trade_id=int(_pick(values, ["agg_trade_id", "aggregate_trade_id", "aggtradeid", "a"])),
        price=float(_pick(values, ["price", "p"])),
        quantity=float(_pick(values, ["quantity", "qty", "q"])),
        first_trade_id=int(_pick(values, ["first_trade_id", "first_tradeid", "firstid", "f"])),
        last_trade_id=int(_pick(values, ["last_trade_id", "last_tradeid", "lastid", "l"])),
        timestamp=_dt_from_ms(_pick(values, ["transact_time", "timestamp", "time", "t"])),
        buyer_is_maker=_bool(_pick(values, ["is_buyer_maker", "buyer_is_maker", "m"])),
        raw=values,
    )


def _looks_like_header(row: list[str]) -> bool:
    joined = ",".join(item.lower() for item in row)
    return "price" in joined or "agg" in joined or "trade" in joined


def _prepend(first: list[str], rows):
    yield first
    yield from rows


def _pick(values: dict[str, str], keys: list[str]) -> str:
    for key in keys:
        if key in values:
            return values[key]
    raise KeyError(f"Missing expected archive column. Tried: {keys}")


def _bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"true", "1", "yes"}


def _dt_from_ms(value: str) -> datetime:
    return datetime.utcfromtimestamp(int(value) / 1000)


def _interval_seconds(interval: str) -> int:
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == "s":
        return max(1, value)
    if unit == "m":
        return max(1, value * 60)
    if unit == "h":
        return max(1, value * 3600)
    raise ValueError(f"Unsupported interval: {interval}")


def _floor_time(value: datetime, seconds: int) -> datetime:
    epoch = int(value.timestamp())
    floored = epoch - (epoch % seconds)
    return datetime.utcfromtimestamp(floored)


def _date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _api_symbol(symbol: str) -> str:
    return symbol.split(":", 1)[0].replace("/", "").upper()


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_").lower()


if __name__ == "__main__":
    raise SystemExit(main())
