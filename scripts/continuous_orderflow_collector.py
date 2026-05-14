from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.market_data import BinanceMarketDataClient, collect_symbol_orderflow_once  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


_STOP = False


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuously collect Binance aggTrades and orderflow bars.")
    parser.add_argument(
        "--symbols",
        default=os.getenv("ORDERFLOW_SYMBOLS", "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT"),
    )
    parser.add_argument(
        "--trading-mode",
        choices=["futures", "spot"],
        default=os.getenv("ORDERFLOW_TRADING_MODE", "futures"),
    )
    parser.add_argument("--poll-seconds", type=int, default=int(os.getenv("ORDERFLOW_POLL_SECONDS", "60")))
    parser.add_argument("--limit", type=int, default=int(os.getenv("ORDERFLOW_LIMIT", "1000")))
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("ORDERFLOW_MAX_PAGES_PER_SYMBOL", "3")))
    parser.add_argument("--bar-interval", default=os.getenv("ORDERFLOW_BAR_INTERVAL", "1m"))
    parser.add_argument(
        "--state-path",
        default=os.getenv("ORDERFLOW_STATE_PATH", "/app/logs/orderflow_collector_state.json"),
    )
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    _install_signal_handlers()
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    if not symbols:
        raise SystemExit("No symbols configured for orderflow collection.")

    state_path = Path(args.state_path)
    state = _load_state(state_path)
    client = BinanceMarketDataClient()
    repository = QuantRepository(args.database_url)

    while not _STOP:
        cycle = {
            "collector": "binance_orderflow",
            "started_at": _utc_now(),
            "symbols": symbols,
            "results": [],
        }
        for symbol in symbols:
            try:
                result = collect_symbol_orderflow_once(
                    symbol=symbol,
                    trading_mode=args.trading_mode,
                    client=client,
                    repository=repository,
                    state=state,
                    limit=args.limit,
                    max_pages=args.max_pages,
                    bar_interval=args.bar_interval,
                )
            except Exception as exc:  # pragma: no cover - defensive loop guard for long-running service
                result = {
                    "symbol": symbol,
                    "trading_mode": args.trading_mode,
                    "status": "error",
                    "error": str(exc),
                }
            cycle["results"].append(result)
            _save_state(state_path, state)

        cycle["finished_at"] = _utc_now()
        print(json.dumps(cycle, ensure_ascii=True), flush=True)
        if args.once:
            return 1 if any(item.get("status") == "error" for item in cycle["results"]) else 0
        _sleep(args.poll_seconds)
    return 0


def _load_state(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp_path.replace(path)


def _sleep(seconds: int) -> None:
    for _ in range(max(1, seconds)):
        if _STOP:
            return
        time.sleep(1)


def _install_signal_handlers() -> None:
    def _handle_stop(_signum: int, _frame: object) -> None:
        global _STOP
        _STOP = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())
