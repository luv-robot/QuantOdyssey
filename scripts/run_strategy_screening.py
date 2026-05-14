import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import DataSufficiencyLevel, StrategyFamily  # noqa: E402
from app.services.harness import (  # noqa: E402
    build_data_sufficiency_gate,
    build_strategy_family_baseline_board,
    decide_strategy_screening_action,
)
from app.services.market_data import load_freqtrade_ohlcv  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen a strategy family and propose next research actions.")
    parser.add_argument("--strategy-family", default=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value)
    parser.add_argument("--universe-report-id")
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--timeframe", action="append", default=[])
    parser.add_argument("--data-dir", default="freqtrade_user_data/data/binance/futures")
    parser.add_argument("--max-candles", type=int, default=20000)
    parser.add_argument(
        "--available-data-level",
        choices=[item.value for item in DataSufficiencyLevel],
        default=DataSufficiencyLevel.L0_OHLCV_ONLY.value,
    )
    parser.add_argument("--save-tasks", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    strategy_family = StrategyFamily(args.strategy_family)
    repository = QuantRepository(args.database_url)
    universe_report = (
        repository.get_failed_breakout_universe_report(args.universe_report_id)
        if args.universe_report_id
        else _latest_failed_breakout_report(repository, strategy_family)
    )
    candles_by_cell = _load_candles(args)
    baseline_board = build_strategy_family_baseline_board(
        candles_by_cell,
        failed_breakout_report=universe_report,
    )
    data_gate = build_data_sufficiency_gate(
        strategy_family=strategy_family,
        available_level=DataSufficiencyLevel(args.available_data_level),
    )
    decision = decide_strategy_screening_action(
        strategy_family=strategy_family,
        universe_report=universe_report,
        regime_coverage=None,
        baseline_board=baseline_board,
        data_gate=data_gate,
    )
    if args.save_tasks:
        for task in decision.next_tasks:
            repository.save_research_task(task)

    print(json.dumps(decision.model_dump(mode="json"), indent=2))
    return 0


def _latest_failed_breakout_report(
    repository: QuantRepository,
    strategy_family: StrategyFamily,
):
    reports = repository.query_failed_breakout_universe_reports(strategy_family=strategy_family.value, limit=1)
    if not reports:
        raise SystemExit("No Failed Breakout universe report found. Run a universe scan first.")
    return reports[0]


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
    return candles_by_cell


def _freqtrade_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


if __name__ == "__main__":
    raise SystemExit(main())
