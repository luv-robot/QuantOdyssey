import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.flows import run_real_data_scout_flow  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Binance market data and generate a MarketSignal.")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--min-rank", type=int, default=70)
    parser.add_argument("--database-url", default="sqlite+pysqlite:///market_data.sqlite3")
    args = parser.parse_args()

    repository = QuantRepository(args.database_url)
    result = run_real_data_scout_flow(
        symbol=args.symbol,
        interval=args.interval,
        min_rank=args.min_rank,
        repository=repository,
    )
    print(
        json.dumps(
            {
                "dataset_prefix": result.dataset_prefix,
                "quality_report": result.quality_report.model_dump(mode="json"),
                "signal": None if result.signal is None else result.signal.model_dump(mode="json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
