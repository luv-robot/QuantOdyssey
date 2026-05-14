import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import (  # noqa: E402
    DataSufficiencyLevel,
    ResearchFinding,
    ResearchFindingSeverity,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    StrategyFamily,
)
from app.services.harness import (  # noqa: E402
    build_failed_breakout_universe_report,
    run_failed_breakout_event_definition_sensitivity,
)
from app.services.market_data import load_freqtrade_ohlcv  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Failed Breakout Punishment event-definition tests across symbols and timeframes."
    )
    parser.add_argument("--task-id")
    parser.add_argument("--thesis-id", default="thesis_failed_breakout_punishment")
    parser.add_argument("--signal-id", default="signal_failed_breakout_universe")
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--timeframe", action="append", default=[])
    parser.add_argument("--data-dir", default="freqtrade_user_data/data/binance/futures")
    parser.add_argument("--side", choices=["short", "long", "both"], default="short")
    parser.add_argument("--horizon-hours", type=int, default=2)
    parser.add_argument("--min-trade-count", type=int, default=50)
    parser.add_argument("--min-market-confirmations", type=int, default=2)
    parser.add_argument(
        "--max-candles",
        type=int,
        default=5000,
        help="Limit each OHLCV cell to the most recent N candles; use 0 for full history.",
    )
    parser.add_argument(
        "--grid",
        choices=["smoke", "full"],
        default="smoke",
        help="Use a small representative grid by default; choose full for the complete 108-trial matrix.",
    )
    parser.add_argument("--max-trials", type=int, default=200)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    symbols = args.symbol or ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    timeframes = args.timeframe or ["5m", "15m"]
    sides = ("short", "long") if args.side == "both" else (args.side,)
    data_dir = Path(args.data_dir)
    repository = QuantRepository(args.database_url) if args.save or args.task_id else None
    task = _load_or_create_task(repository, args)
    reports = []
    skipped_cells: list[str] = []

    for symbol in symbols:
        for timeframe in timeframes:
            ohlcv_file = data_dir / f"{_freqtrade_symbol(symbol)}-{timeframe}-futures.feather"
            if not ohlcv_file.exists():
                skipped_cells.append(f"{symbol}:{timeframe}:missing_ohlcv")
                continue
            candles = load_freqtrade_ohlcv(ohlcv_file, symbol, timeframe)
            if args.max_candles > 0 and len(candles) > args.max_candles:
                candles = candles[-args.max_candles :]
            grid_kwargs = _grid_kwargs(args.grid)
            report = run_failed_breakout_event_definition_sensitivity(
                task=task,
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                sides=sides,
                horizon_hours=args.horizon_hours,
                min_trade_count=args.min_trade_count,
                max_trials=args.max_trials,
                **grid_kwargs,
            )
            reports.append(report)
            if args.save and repository is not None:
                repository.save_failed_breakout_sensitivity_report(report)

    universe_report = build_failed_breakout_universe_report(
        task=task,
        reports=reports,
        skipped_cells=skipped_cells,
        min_market_confirmations=args.min_market_confirmations,
        min_trade_count=args.min_trade_count,
    )

    if args.save and repository is not None:
        repository.save_failed_breakout_universe_report(universe_report)
        repository.save_research_task(task.model_copy(update={"status": ResearchTaskStatus.COMPLETED}))
        if task.signal_id:
            repository.save_research_finding(_finding_from_report(universe_report, task))

    print(json.dumps(universe_report.model_dump(mode="json"), indent=2))
    return 0 if universe_report.completed_cells > 0 else 2


def _load_or_create_task(repository: QuantRepository | None, args: argparse.Namespace) -> ResearchTask:
    if args.task_id and repository is not None:
        task = repository.get_research_task(args.task_id)
        if task is None:
            raise SystemExit(f"ResearchTask not found: {args.task_id}")
        return task.model_copy(update={"status": ResearchTaskStatus.RUNNING})
    return ResearchTask(
        task_id=args.task_id or f"task_failed_breakout_universe_{uuid4().hex[:8]}",
        task_type=ResearchTaskType.CROSS_SYMBOL_TEST,
        subject_type="strategy_family",
        subject_id=StrategyFamily.FAILED_BREAKOUT_PUNISHMENT.value,
        thesis_id=args.thesis_id,
        signal_id=args.signal_id,
        hypothesis="Failed Breakout Punishment should produce enough OHLCV-observable events to justify deeper research.",
        rationale=(
            "Funding Crowding Fade frequency was too low under current data; this template tests a naturally "
            "higher-frequency market microstructure idea before spending optimizer budget."
        ),
        required_experiments=[
            "run OHLCV-only failed-breakout matrix across BTC/ETH/SOL",
            "compare 5m and 15m cells",
            "identify trial ids that beat simple failed-breakout baseline in multiple cells",
        ],
        success_metrics=["same trial id is robust in at least two cells", "best cells meet sample floor"],
        failure_conditions=["sample count collapses", "best trials do not beat simple failed-breakout baseline"],
        required_data_level=DataSufficiencyLevel.L0_OHLCV_ONLY,
        estimated_cost=60,
        priority_score=91,
        status=ResearchTaskStatus.RUNNING,
        approval_required=False,
        autonomy_level=2,
    )


def _finding_from_report(report, task: ResearchTask) -> ResearchFinding:
    severity = ResearchFindingSeverity.LOW if report.robust_trial_ids else ResearchFindingSeverity.MEDIUM
    return ResearchFinding(
        finding_id=f"finding_{report.report_id}_{uuid4().hex[:8]}",
        thesis_id=task.thesis_id,
        signal_id=task.signal_id or report.signal_id or "signal_failed_breakout_universe",
        strategy_id=task.strategy_id,
        finding_type="failed_breakout_universe_scan",
        severity=severity,
        summary="Failed Breakout Punishment event-definition universe scan completed.",
        observations=report.findings,
        evidence_gaps=report.skipped_cells,
        next_task_ids=[],
        evidence_refs=[f"failed_breakout_universe_report:{report.report_id}", f"research_task:{task.task_id}"],
    )


def _freqtrade_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


def _grid_kwargs(grid: str) -> dict:
    if grid == "full":
        return {}
    return {
        "level_sources": ("rolling_extreme", "swing_extreme"),
        "level_lookback_bars": (48, 96),
        "level_quality_thresholds": (0,),
        "breakout_depth_bps": (10, 25, 50),
        "acceptance_window_bars": (3, 6),
        "acceptance_failure_thresholds": (0,),
        "volume_zscore_thresholds": (0, 1.5),
    }


if __name__ == "__main__":
    raise SystemExit(main())
