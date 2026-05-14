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
    build_event_definition_universe_report,
    run_funding_crowding_event_definition_sensitivity,
)
from app.services.market_data import (  # noqa: E402
    find_freqtrade_funding_file,
    find_open_interest_file,
    load_freqtrade_funding_rates,
    load_freqtrade_ohlcv,
    load_open_interest_points,
)
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Funding Crowding Fade event-definition tests across symbols and timeframes."
    )
    parser.add_argument("--task-id")
    parser.add_argument("--thesis-id", default="thesis_funding_crowding_fade")
    parser.add_argument("--signal-id", default="signal_event_definition_universe")
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--timeframe", action="append", default=[])
    parser.add_argument("--data-dir", default="freqtrade_user_data/data/binance/futures")
    parser.add_argument("--horizon-hours", type=int, default=4)
    parser.add_argument("--min-trade-count", type=int, default=20)
    parser.add_argument("--min-market-confirmations", type=int, default=2)
    parser.add_argument("--max-trials", type=int, default=200)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    symbols = args.symbol or ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    timeframes = args.timeframe or ["5m", "15m"]
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
            funding_file = find_freqtrade_funding_file(ohlcv_file, symbol, timeframe)
            if funding_file is None:
                skipped_cells.append(f"{symbol}:{timeframe}:missing_funding")
                continue
            oi_file = find_open_interest_file(ohlcv_file, symbol, timeframe) or _fallback_open_interest_file(
                data_dir, symbol
            )
            candles = load_freqtrade_ohlcv(ohlcv_file, symbol, timeframe)
            funding_rates = load_freqtrade_funding_rates(funding_file, symbol)
            open_interest_points = None if oi_file is None else load_open_interest_points(oi_file, symbol)
            report = run_funding_crowding_event_definition_sensitivity(
                task=task,
                candles=candles,
                funding_rates=funding_rates,
                open_interest_points=open_interest_points,
                symbol=symbol,
                timeframe=timeframe,
                horizon_hours=args.horizon_hours,
                min_trade_count=args.min_trade_count,
                max_trials=args.max_trials,
            )
            reports.append(report)
            if args.save and repository is not None:
                repository.save_event_definition_sensitivity_report(report)

    universe_report = build_event_definition_universe_report(
        task=task,
        reports=reports,
        skipped_cells=skipped_cells,
        min_market_confirmations=args.min_market_confirmations,
        min_trade_count=args.min_trade_count,
    )

    if args.save and repository is not None:
        repository.save_event_definition_universe_report(universe_report)
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
        task_id=args.task_id or f"task_event_definition_universe_{uuid4().hex[:8]}",
        task_type=ResearchTaskType.CROSS_SYMBOL_TEST,
        subject_type="strategy_family",
        subject_id=StrategyFamily.FUNDING_CROWDING_FADE.value,
        thesis_id=args.thesis_id,
        signal_id=args.signal_id,
        hypothesis="A useful Funding Crowding Fade event definition should not only work in one symbol/timeframe cell.",
        rationale="Single-market best cells are weak evidence; the Harness needs cross-market stability before optimizer work.",
        required_experiments=[
            "run event-definition matrix across BTC/ETH/SOL",
            "compare 5m and 15m cells",
            "identify trial ids that are robust in multiple cells",
        ],
        success_metrics=["same trial id is robust in at least two cells", "best cells meet sample floor"],
        failure_conditions=["all positive cells are isolated", "sample count collapses outside one market"],
        required_data_level=DataSufficiencyLevel.L1_FUNDING_OI,
        estimated_cost=80,
        priority_score=90,
        status=ResearchTaskStatus.RUNNING,
        approval_required=False,
        autonomy_level=2,
    )


def _finding_from_report(report, task: ResearchTask) -> ResearchFinding:
    severity = ResearchFindingSeverity.LOW if report.robust_trial_ids else ResearchFindingSeverity.MEDIUM
    return ResearchFinding(
        finding_id=f"finding_{report.report_id}_{uuid4().hex[:8]}",
        thesis_id=task.thesis_id,
        signal_id=task.signal_id or report.signal_id or "signal_event_definition_universe",
        strategy_id=task.strategy_id,
        finding_type="event_definition_universe_scan",
        severity=severity,
        summary="Funding Crowding Fade event-definition universe scan completed.",
        observations=report.findings,
        evidence_gaps=report.skipped_cells,
        next_task_ids=[],
        evidence_refs=[f"event_definition_universe_report:{report.report_id}", f"research_task:{task.task_id}"],
    )


def _fallback_open_interest_file(data_dir: Path, symbol: str) -> Path | None:
    base = _freqtrade_symbol(symbol)
    candidates = [
        data_dir / f"{base}-5m-open_interest.json",
        data_dir / f"{base}-5m-open_interest.feather",
    ]
    return next((path for path in candidates if path.exists()), None)


def _freqtrade_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


if __name__ == "__main__":
    raise SystemExit(main())
