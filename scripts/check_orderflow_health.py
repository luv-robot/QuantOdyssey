import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.market_data import build_orderflow_health_report  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check continuous orderflow collector freshness.")
    parser.add_argument(
        "--symbols",
        default=os.getenv("ORDERFLOW_HEALTH_SYMBOLS")
        or os.getenv("ORDERFLOW_SYMBOLS", "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT"),
    )
    parser.add_argument("--interval", default=os.getenv("ORDERFLOW_BAR_INTERVAL", "1m"))
    parser.add_argument("--trading-mode", default=os.getenv("ORDERFLOW_TRADING_MODE", "futures"))
    parser.add_argument(
        "--max-staleness-seconds",
        type=int,
        default=int(os.getenv("ORDERFLOW_MAX_STALENESS_SECONDS", "600")),
    )
    parser.add_argument("--state-path", default=os.getenv("ORDERFLOW_STATE_PATH", "/app/logs/orderflow_collector_state.json"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    args = parser.parse_args()

    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    report = build_orderflow_health_report(
        QuantRepository(args.database_url),
        symbols=symbols,
        interval=args.interval,
        trading_mode=args.trading_mode,
        max_staleness_seconds=args.max_staleness_seconds,
        state_path=args.state_path,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
