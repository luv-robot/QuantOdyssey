import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.harness import HarnessRunnerConfig, run_research_harness_queue  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run low-risk proposed Harness research tasks.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    parser.add_argument("--data-dir", default="freqtrade_user_data/data/binance/futures")
    parser.add_argument("--scratchpad-dir", default=".qo/scratchpad")
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--timeframe", action="append", default=[])
    parser.add_argument("--max-tasks", type=int, default=5)
    parser.add_argument("--max-queue-scan", type=int, default=50)
    parser.add_argument("--max-candles", type=int, default=5000)
    parser.add_argument("--max-trials", type=int, default=80)
    parser.add_argument("--min-trade-count", type=int, default=20)
    args = parser.parse_args()

    config = HarnessRunnerConfig(
        data_dir=Path(args.data_dir),
        scratchpad_base_dir=Path(args.scratchpad_dir),
        symbols=tuple(args.symbol or ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]),
        timeframes=tuple(args.timeframe or ["5m", "15m"]),
        max_tasks=args.max_tasks,
        max_queue_scan=args.max_queue_scan,
        max_candles=args.max_candles,
        max_trials=args.max_trials,
        min_trade_count=args.min_trade_count,
    )
    repository = QuantRepository(args.database_url)
    summary = run_research_harness_queue(repository, config=config)
    print(json.dumps(_summary_dict(summary), indent=2))
    return 0


def _summary_dict(summary) -> dict:
    return {
        "run_id": summary.run_id,
        "considered": summary.considered,
        "executed": summary.executed,
        "skipped": summary.skipped,
        "completed": summary.completed,
        "blocked": summary.blocked,
        "scratchpad_path": summary.scratchpad_path,
        "results": [
            {
                "task_id": result.task_id,
                "task_type": result.task_type,
                "status": result.status.value,
                "finding_ids": result.finding_ids,
                "artifact_refs": result.artifact_refs,
                "skipped_reason": result.skipped_reason,
            }
            for result in summary.results
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
