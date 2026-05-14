import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import StrategyFamily  # noqa: E402
from app.services.harness import scan_failed_breakout_trial_events  # noqa: E402
from app.services.market_data import load_freqtrade_ohlcv  # noqa: E402
from app.storage import QuantRepository  # noqa: E402
from scripts.backfill_binance_agg_trades_archive import (  # noqa: E402
    _archive_url,
    _download_archive_orderflow_bars,
    _safe_symbol,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill Binance orderflow archive dates that overlap Failed Breakout events."
    )
    parser.add_argument("--strategy-family", default=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value)
    parser.add_argument("--universe-report-id")
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--timeframe", action="append", default=[])
    parser.add_argument("--data-dir", default="freqtrade_user_data/data/binance/futures")
    parser.add_argument("--max-candles", type=int, default=20000)
    parser.add_argument("--horizon-hours", type=int, default=2)
    parser.add_argument("--max-events-per-cell", type=int, default=100)
    parser.add_argument("--context-days-before", type=int, default=0)
    parser.add_argument("--context-days-after", type=int, default=0)
    parser.add_argument("--trading-mode", choices=["futures", "spot"], default="futures")
    parser.add_argument("--bar-interval", default=os.getenv("ORDERFLOW_BAR_INTERVAL", "1m"))
    parser.add_argument("--max-days", type=int, default=3)
    parser.add_argument("--max-rows-per-file", type=int, default=0)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--include-existing", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    strategy_family = StrategyFamily(args.strategy_family)
    if strategy_family != StrategyFamily.FAILED_BREAKOUT_PUNISHMENT:
        raise SystemExit("Only failed_breakout_punishment event-window backfill is implemented.")

    repository = QuantRepository(args.database_url)
    universe_report = (
        repository.get_failed_breakout_universe_report(args.universe_report_id)
        if args.universe_report_id
        else _latest_failed_breakout_report(repository, strategy_family)
    )
    if universe_report is None:
        raise SystemExit("No Failed Breakout universe report found.")

    symbols = set(args.symbol or universe_report.symbols)
    timeframes = set(args.timeframe or universe_report.timeframes)
    event_dates = _event_dates_by_symbol(
        universe_report=universe_report,
        symbols=symbols,
        timeframes=timeframes,
        data_dir=Path(args.data_dir),
        max_candles=args.max_candles,
        horizon_hours=args.horizon_hours,
        max_events_per_cell=args.max_events_per_cell,
        context_days_before=args.context_days_before,
        context_days_after=args.context_days_after,
    )
    plan = _build_backfill_plan(
        repository=repository,
        event_dates=event_dates,
        interval=args.bar_interval,
        include_existing=args.include_existing,
        max_days=args.max_days,
    )
    results = []
    if args.execute:
        results = _execute_backfill_plan(
            repository=repository,
            plan=plan,
            trading_mode=args.trading_mode,
            interval=args.bar_interval,
            max_rows_per_file=args.max_rows_per_file,
            sleep_seconds=args.sleep_seconds,
        )

    print(
        json.dumps(
            {
                "universe_report_id": universe_report.report_id,
                "execute": args.execute,
                "max_days": args.max_days,
                "candidate_date_count": sum(len(days) for days in event_dates.values()),
                "planned_date_count": sum(len(items) for items in plan.values()),
                "plan": {
                    symbol: [item | {"date": item["date"].isoformat()} for item in items]
                    for symbol, items in plan.items()
                },
                "results": results,
            },
            indent=2,
        )
    )
    return 0


def _latest_failed_breakout_report(repository: QuantRepository, strategy_family: StrategyFamily):
    reports = repository.query_failed_breakout_universe_reports(strategy_family=strategy_family.value, limit=1)
    if not reports:
        raise SystemExit("No Failed Breakout universe report found. Run a universe scan first.")
    return reports[0]


def _event_dates_by_symbol(
    *,
    universe_report,
    symbols: set[str],
    timeframes: set[str],
    data_dir: Path,
    max_candles: int,
    horizon_hours: int,
    max_events_per_cell: int,
    context_days_before: int,
    context_days_after: int,
) -> dict[str, dict[date, int]]:
    dates_by_symbol: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for cell in universe_report.cells:
        if cell.symbol not in symbols or cell.timeframe not in timeframes or cell.best_trial_id is None:
            continue
        path = data_dir / f"{_freqtrade_symbol(cell.symbol)}-{cell.timeframe}-futures.feather"
        if not path.exists():
            continue
        candles = load_freqtrade_ohlcv(path, cell.symbol, cell.timeframe)
        if max_candles > 0 and len(candles) > max_candles:
            candles = candles[-max_candles:]
        events = scan_failed_breakout_trial_events(
            candles,
            timeframe=cell.timeframe,
            trial_id=cell.best_trial_id,
            horizon_hours=horizon_hours,
        )
        for event in events[-max_events_per_cell:]:
            event_day = _as_date(event["event_time"])
            for offset in range(-context_days_before, context_days_after + 1):
                dates_by_symbol[cell.symbol][event_day + timedelta(days=offset)] += 1
    return {symbol: dict(days) for symbol, days in dates_by_symbol.items()}


def _build_backfill_plan(
    *,
    repository: QuantRepository,
    event_dates: dict[str, dict[date, int]],
    interval: str,
    include_existing: bool,
    max_days: int,
) -> dict[str, list[dict]]:
    remaining = max(0, max_days)
    plan: dict[str, list[dict]] = {}
    for symbol in sorted(event_dates):
        items = []
        for day, event_count in sorted(event_dates[symbol].items()):
            existing_count = len(
                repository.query_orderflow_bars(
                    symbol,
                    interval=interval,
                    start_time=_day_start(day),
                    end_time=_day_start(day + timedelta(days=1)),
                    limit=1,
                )
            )
            if existing_count and not include_existing:
                continue
            if remaining <= 0:
                break
            items.append(
                {
                    "symbol": symbol,
                    "date": day,
                    "event_count": event_count,
                    "already_has_orderflow": bool(existing_count),
                }
            )
            remaining -= 1
        if items:
            plan[symbol] = items
        if remaining <= 0:
            break
    return plan


def _execute_backfill_plan(
    *,
    repository: QuantRepository,
    plan: dict[str, list[dict]],
    trading_mode: str,
    interval: str,
    max_rows_per_file: int,
    sleep_seconds: float,
) -> list[dict]:
    results = []
    for symbol, items in plan.items():
        cvd = 0.0
        for item in items:
            day = item["date"]
            url = _archive_url(symbol, day, trading_mode)
            try:
                bars, trade_count = _download_archive_orderflow_bars(
                    symbol,
                    url,
                    interval=interval,
                    start_cvd=cvd,
                    max_rows=max_rows_per_file,
                )
            except HTTPError as exc:
                results.append(
                    {
                        "symbol": symbol,
                        "date": day.isoformat(),
                        "status": "missing" if exc.code == 404 else "error",
                        "http_code": exc.code,
                        "url": url,
                    }
                )
                continue
            if bars:
                cvd = bars[-1].cumulative_volume_delta
            dataset_prefix = f"binance:{trading_mode}:event_archive_agg_trades:{_safe_symbol(symbol)}:{day:%Y%m%d}"
            repository.save_orderflow_bars(f"{dataset_prefix}:orderflow:{interval}", symbol, bars)
            results.append(
                {
                    "symbol": symbol,
                    "date": day.isoformat(),
                    "status": "saved",
                    "trade_count": trade_count,
                    "bar_count": len(bars),
                    "event_count": item["event_count"],
                    "orderflow_dataset_id": f"{dataset_prefix}:orderflow:{interval}",
                    "url": url,
                }
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    return results


def _freqtrade_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _day_start(day: date) -> datetime:
    return datetime.combine(day, dt_time.min)


if __name__ == "__main__":
    raise SystemExit(main())
