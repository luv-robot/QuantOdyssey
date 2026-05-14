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

from app.models import AggregateTrade  # noqa: E402
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
                trades = _download_archive_trades(symbol, url, max_rows=args.max_rows_per_file)
            except HTTPError as exc:
                if exc.code == 404 and not args.fail_on_missing:
                    results.append({"symbol": symbol, "date": day.isoformat(), "status": "missing", "url": url})
                    continue
                raise
            bars = build_orderflow_bars(trades, interval=args.bar_interval, start_cvd=cvd)
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
                    "trade_count": len(trades),
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


def _download_archive_trades(symbol: str, url: str, *, max_rows: int = 0) -> list[AggregateTrade]:
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
            trades = []
            for index, row in enumerate(data_rows):
                if max_rows and index >= max_rows:
                    break
                if not row:
                    continue
                trades.append(_row_to_trade(symbol, row, header))
    return trades


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
