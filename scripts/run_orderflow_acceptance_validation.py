import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import StrategyFamily  # noqa: E402
from app.services.harness import run_failed_breakout_orderflow_acceptance_validation  # noqa: E402
from app.services.market_data import load_freqtrade_ohlcv  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Failed Breakout events with orderflow bars.")
    parser.add_argument("--strategy-family", default=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value)
    parser.add_argument("--universe-report-id")
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--timeframe", action="append", default=[])
    parser.add_argument("--data-dir", default="freqtrade_user_data/data/binance/futures")
    parser.add_argument("--max-candles", type=int, default=20000)
    parser.add_argument("--horizon-hours", type=int, default=2)
    parser.add_argument("--max-events-per-cell", type=int, default=100)
    parser.add_argument("--orderflow-interval", default=os.getenv("ORDERFLOW_BAR_INTERVAL", "1m"))
    parser.add_argument("--max-orderflow-bars", type=int, default=200000)
    parser.add_argument("--min-events-with-orderflow", type=int, default=30)
    parser.add_argument("--min-confirmation-rate", type=float, default=0.5)
    parser.add_argument("--max-conflict-rate", type=float, default=0.35)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    strategy_family = StrategyFamily(args.strategy_family)
    if strategy_family != StrategyFamily.FAILED_BREAKOUT_PUNISHMENT:
        raise SystemExit("Only failed_breakout_punishment orderflow validation is implemented.")

    repository = QuantRepository(args.database_url)
    universe_report = (
        repository.get_failed_breakout_universe_report(args.universe_report_id)
        if args.universe_report_id
        else _latest_failed_breakout_report(repository, strategy_family)
    )
    symbols = args.symbol or universe_report.symbols or ["BTC/USDT:USDT"]
    timeframes = args.timeframe or universe_report.timeframes or ["1h"]
    candles_by_cell = _load_candles(args, symbols, timeframes)
    orderflow_by_cell = _load_orderflow(
        repository,
        symbols,
        timeframes,
        args.orderflow_interval,
        args.max_orderflow_bars,
    )
    report = run_failed_breakout_orderflow_acceptance_validation(
        universe_report=universe_report,
        candles_by_cell=candles_by_cell,
        orderflow_by_cell=orderflow_by_cell,
        horizon_hours=args.horizon_hours,
        max_events_per_cell=args.max_events_per_cell,
        min_events_with_orderflow=args.min_events_with_orderflow,
        min_confirmation_rate=args.min_confirmation_rate,
        max_conflict_rate=args.max_conflict_rate,
    )
    if args.save:
        repository.save_strategy_family_orderflow_acceptance_report(report)
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    return 0


def _latest_failed_breakout_report(
    repository: QuantRepository,
    strategy_family: StrategyFamily,
):
    reports = repository.query_failed_breakout_universe_reports(strategy_family=strategy_family.value, limit=1)
    if not reports:
        raise SystemExit("No Failed Breakout universe report found. Run a universe scan first.")
    return reports[0]


def _load_candles(args: argparse.Namespace, symbols: list[str], timeframes: list[str]):
    data_dir = Path(args.data_dir)
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
    return candles_by_cell


def _load_orderflow(
    repository: QuantRepository,
    symbols: list[str],
    timeframes: list[str],
    orderflow_interval: str,
    max_orderflow_bars: int,
):
    orderflow_by_cell = {}
    for symbol in symbols:
        bars = repository.query_orderflow_bars(
            symbol,
            interval=orderflow_interval,
            limit=max_orderflow_bars,
        )
        for timeframe in timeframes:
            orderflow_by_cell[(symbol, timeframe)] = sorted(bars, key=lambda item: item.open_time)
    return orderflow_by_cell


def _freqtrade_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


if __name__ == "__main__":
    raise SystemExit(main())
