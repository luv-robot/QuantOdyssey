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
from app.services.harness import run_funding_crowding_event_definition_sensitivity  # noqa: E402
from app.services.market_data import (  # noqa: E402
    load_freqtrade_funding_rates,
    load_freqtrade_ohlcv,
    load_open_interest_points,
)
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a bounded Funding Crowding Fade event-definition sensitivity test."
    )
    parser.add_argument("--task-id")
    parser.add_argument("--thesis-id", default="thesis_funding_crowding_fade")
    parser.add_argument("--signal-id", default="signal_manual_event_definition")
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--ohlcv-file", required=True)
    parser.add_argument("--funding-file", required=True)
    parser.add_argument("--open-interest-file")
    parser.add_argument("--horizon-hours", type=int, default=4)
    parser.add_argument("--min-trade-count", type=int, default=20)
    parser.add_argument("--max-trials", type=int, default=200)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    repository = QuantRepository(args.database_url) if args.save or args.task_id else None
    task = _load_or_create_task(repository, args)
    candles = load_freqtrade_ohlcv(Path(args.ohlcv_file), args.symbol, args.timeframe)
    funding_rates = load_freqtrade_funding_rates(Path(args.funding_file), args.symbol)
    open_interest_points = (
        None
        if args.open_interest_file is None
        else load_open_interest_points(Path(args.open_interest_file), args.symbol)
    )
    report = run_funding_crowding_event_definition_sensitivity(
        task=task,
        candles=candles,
        funding_rates=funding_rates,
        open_interest_points=open_interest_points,
        symbol=args.symbol,
        timeframe=args.timeframe,
        horizon_hours=args.horizon_hours,
        min_trade_count=args.min_trade_count,
        max_trials=args.max_trials,
    )

    if args.save and repository is not None:
        repository.save_event_definition_sensitivity_report(report)
        repository.save_research_task(task.model_copy(update={"status": ResearchTaskStatus.COMPLETED}))
        if task.signal_id:
            repository.save_research_finding(_finding_from_report(report, task))

    print(json.dumps(report.model_dump(mode="json"), indent=2))
    return 0 if report.completed_trials > 0 else 2


def _load_or_create_task(repository: QuantRepository | None, args: argparse.Namespace) -> ResearchTask:
    if args.task_id and repository is not None:
        task = repository.get_research_task(args.task_id)
        if task is None:
            raise SystemExit(f"ResearchTask not found: {args.task_id}")
        return task.model_copy(update={"status": ResearchTaskStatus.RUNNING})
    return ResearchTask(
        task_id=args.task_id or f"task_event_definition_{StrategyFamily.FUNDING_CROWDING_FADE.value}_{uuid4().hex[:8]}",
        task_type=ResearchTaskType.EVENT_DEFINITION_TEST,
        subject_type="strategy_family",
        subject_id=StrategyFamily.FUNDING_CROWDING_FADE.value,
        thesis_id=args.thesis_id,
        signal_id=args.signal_id,
        hypothesis="Funding Crowding Fade may require funding, OI, failed-breakout, and OI-retreat conditions together.",
        rationale="Run a bounded declared matrix before open-ended optimizer work.",
        required_experiments=[
            "funding_percentile thresholds 90/95/97.5",
            "OI_percentile thresholds 75/85/90",
            "failed-breakout windows 3/6/12 bars",
            "OI retreat confirmation none/0.5%/1%/2%",
        ],
        success_metrics=["stable region beats cash", "stable region beats funding-only baseline"],
        failure_conditions=["sample count collapses", "only an isolated parameter cell works"],
        required_data_level=DataSufficiencyLevel.L1_FUNDING_OI,
        estimated_cost=40,
        priority_score=92,
        status=ResearchTaskStatus.RUNNING,
        approval_required=False,
        autonomy_level=2,
    )


def _finding_from_report(report, task: ResearchTask) -> ResearchFinding:
    severity = ResearchFindingSeverity.LOW if report.robust_trial_count >= 3 else ResearchFindingSeverity.MEDIUM
    return ResearchFinding(
        finding_id=f"finding_{report.report_id}_{uuid4().hex[:8]}",
        thesis_id=task.thesis_id,
        signal_id=task.signal_id or report.signal_id or "signal_manual_event_definition",
        strategy_id=task.strategy_id,
        finding_type="event_definition_sensitivity",
        severity=severity,
        summary="Funding Crowding Fade event-definition sensitivity test completed.",
        observations=report.findings,
        evidence_gaps=report.data_warnings,
        next_task_ids=[],
        evidence_refs=[f"event_definition_sensitivity_report:{report.report_id}", f"research_task:{task.task_id}"],
    )


if __name__ == "__main__":
    raise SystemExit(main())
