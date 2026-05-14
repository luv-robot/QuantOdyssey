import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import ResearchFinding, ResearchFindingSeverity, StrategyFamily  # noqa: E402
from app.services.harness import (  # noqa: E402
    run_failed_breakout_bootstrap_monte_carlo,
    run_failed_breakout_walk_forward_validation,
)
from app.services.market_data import load_freqtrade_ohlcv  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run validation follow-ups produced by the strategy screening decision layer."
    )
    parser.add_argument("--strategy-family", default=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value)
    parser.add_argument("--universe-report-id")
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--timeframe", action="append", default=[])
    parser.add_argument("--data-dir", default="freqtrade_user_data/data/binance/futures")
    parser.add_argument("--max-candles", type=int, default=20000)
    parser.add_argument("--folds", type=int, default=3)
    parser.add_argument("--min-trades-per-window", type=int, default=20)
    parser.add_argument("--horizon-hours", type=int, default=2)
    parser.add_argument("--simulations", type=int, default=500)
    parser.add_argument("--horizon-trades", type=int, default=100)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--expensive-simulation-threshold", type=int, default=250_000)
    parser.add_argument("--approve-expensive-monte-carlo", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    strategy_family = StrategyFamily(args.strategy_family)
    if strategy_family != StrategyFamily.FAILED_BREAKOUT_PUNISHMENT:
        raise SystemExit("Only failed_breakout_punishment follow-up validation is implemented.")

    repository = QuantRepository(args.database_url)
    universe_report = (
        repository.get_failed_breakout_universe_report(args.universe_report_id)
        if args.universe_report_id
        else _latest_failed_breakout_report(repository, strategy_family)
    )
    candles_by_cell = _load_candles(args)
    walk_forward = run_failed_breakout_walk_forward_validation(
        universe_report=universe_report,
        candles_by_cell=candles_by_cell,
        folds=args.folds,
        min_trades_per_window=args.min_trades_per_window,
        horizon_hours=args.horizon_hours,
    )
    monte_carlo = run_failed_breakout_bootstrap_monte_carlo(
        universe_report=universe_report,
        candles_by_cell=candles_by_cell,
        simulations=args.simulations,
        horizon_trades=args.horizon_trades,
        seed=args.seed,
        expensive_simulation_threshold=args.expensive_simulation_threshold,
        approved_to_run=args.approve_expensive_monte_carlo,
        horizon_hours=args.horizon_hours,
    )

    if args.save:
        repository.save_strategy_family_walk_forward_report(walk_forward)
        repository.save_strategy_family_monte_carlo_report(monte_carlo)
        repository.save_research_finding(_finding_from_reports(universe_report, walk_forward, monte_carlo))

    print(
        json.dumps(
            {
                "walk_forward": walk_forward.model_dump(mode="json"),
                "monte_carlo": monte_carlo.model_dump(mode="json"),
            },
            indent=2,
        )
    )
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


def _finding_from_reports(universe_report, walk_forward, monte_carlo) -> ResearchFinding:
    severity = (
        ResearchFindingSeverity.LOW
        if walk_forward.passed and monte_carlo.passed
        else ResearchFindingSeverity.MEDIUM
    )
    if not walk_forward.passed and not monte_carlo.passed:
        severity = ResearchFindingSeverity.HIGH
    return ResearchFinding(
        finding_id=f"finding_strategy_validation_{uuid4().hex[:8]}",
        thesis_id=universe_report.thesis_id,
        signal_id=universe_report.signal_id or "signal_failed_breakout_universe",
        strategy_id=None,
        finding_type="strategy_family_validation_followup",
        severity=severity,
        summary="Strategy screening follow-up validation completed.",
        observations=[
            *walk_forward.findings,
            *monte_carlo.findings,
        ],
        evidence_gaps=[],
        next_task_ids=[],
        evidence_refs=[
            f"failed_breakout_universe_report:{universe_report.report_id}",
            f"strategy_family_walk_forward_report:{walk_forward.report_id}",
            f"strategy_family_monte_carlo_report:{monte_carlo.report_id}",
        ],
    )


def _freqtrade_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


if __name__ == "__main__":
    raise SystemExit(main())
