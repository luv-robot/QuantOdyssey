import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.market_data import build_funding_crowding_fade_event  # noqa: E402
from app.storage import QuantRepository  # noqa: E402
from scripts.import_freqtrade_market_data import (  # noqa: E402
    load_freqtrade_funding_rates,
    load_freqtrade_ohlcv,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a traceable Funding Crowding Fade signal from Freqtrade futures data."
    )
    parser.add_argument("--thesis-id", default="thesis_funding_crowding_fade")
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--ohlcv-file", required=True)
    parser.add_argument("--funding-file", required=True)
    parser.add_argument("--min-rank", type=int, default=60)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    candles = load_freqtrade_ohlcv(Path(args.ohlcv_file), args.symbol, args.timeframe)
    funding_rates = load_freqtrade_funding_rates(Path(args.funding_file), args.symbol)
    result = build_funding_crowding_fade_event(
        thesis_id=args.thesis_id,
        symbol=args.symbol,
        timeframe=args.timeframe,
        candles=candles,
        funding_rates=funding_rates,
        min_rank=args.min_rank,
    )
    if args.save and result.signal is not None and result.event_episode is not None:
        repository = QuantRepository(args.database_url)
        repository.save_signal(result.signal)
        repository.save_event_episode(result.event_episode)

    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0 if result.signal is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
