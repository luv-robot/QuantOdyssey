import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from app.flows.human_research_pipeline import run_human_research_pipeline  # noqa: E402
from app.models import MarketSignal, MonteCarloBacktestConfig, ResearchThesis, ThesisStatus  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the human-led strategy research pipeline.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--market-observation", required=True)
    parser.add_argument("--hypothesis", required=True)
    parser.add_argument("--trade-logic", required=True)
    parser.add_argument("--expected-regime", action="append", default=[])
    parser.add_argument("--invalidation-condition", action="append", default=[])
    parser.add_argument("--risk-note", action="append", default=[])
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--signal-id")
    parser.add_argument("--candidate-count", type=int, default=3)
    parser.add_argument("--backtest-mode", choices=["real", "mock"], default=None)
    parser.add_argument("--mc-simulations", type=int, default=500)
    parser.add_argument("--mc-horizon-trades", type=int, default=100)
    parser.add_argument("--mc-threshold", type=int, default=250_000)
    parser.add_argument("--approve-expensive-monte-carlo", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_url = os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3")
    repository = QuantRepository(database_url)
    signal = _load_signal(database_url, args.signal_id)
    thesis = ResearchThesis(
        thesis_id=f"thesis_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}",
        title=args.title,
        status=ThesisStatus.READY_FOR_IMPLEMENTATION,
        market_observation=args.market_observation,
        hypothesis=args.hypothesis,
        trade_logic=args.trade_logic,
        expected_regimes=args.expected_regime or ["unspecified"],
        invalidation_conditions=args.invalidation_condition or ["Thesis invalidation not specified."],
        risk_notes=args.risk_note,
        linked_signal_ids=[signal.signal_id],
        constraints=args.constraint,
    )
    result = run_human_research_pipeline(
        thesis,
        signal,
        repository,
        candidate_count=args.candidate_count,
        monte_carlo_config=MonteCarloBacktestConfig(
            simulations=args.mc_simulations,
            horizon_trades=args.mc_horizon_trades,
            expensive_simulation_threshold=args.mc_threshold,
        ),
        approve_expensive_monte_carlo=args.approve_expensive_monte_carlo,
        backtest_mode=args.backtest_mode,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0 if result.selected_candidate_id else 2


def _load_signal(database_url: str, signal_id: str | None) -> MarketSignal:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        if signal_id:
            row = connection.execute(
                text("select payload from signals where signal_id = :signal_id"),
                {"signal_id": signal_id},
            ).fetchone()
        else:
            row = connection.execute(
                text("select payload from signals order by created_at desc limit 1")
            ).fetchone()
    if row is None:
        raise SystemExit("No MarketSignal found. Import or generate data before running research.")
    return MarketSignal.model_validate_json(row[0])


if __name__ == "__main__":
    raise SystemExit(main())
