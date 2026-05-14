from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def build_orderflow_health_report(
    repository: Any,
    *,
    symbols: list[str],
    interval: str = "1m",
    trading_mode: str = "futures",
    max_staleness_seconds: int = 600,
    recent_window_minutes: int = 15,
    state_path: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.utcnow()
    state = _load_state(state_path)
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        latest_bar = repository.get_latest_orderflow_bar(symbol, interval=interval)
        recent_count = repository.count_orderflow_bars(
            symbol,
            interval=interval,
            start_time=now - timedelta(minutes=recent_window_minutes),
        )
        state_key = f"{trading_mode}:{symbol.upper()}"
        state_item = state.get(state_key, {})
        if latest_bar is None:
            rows.append(
                {
                    "symbol": symbol,
                    "status": "fail",
                    "message": "No orderflow bars found.",
                    "latest_bar_close_time": None,
                    "lag_seconds": None,
                    "recent_bar_count": recent_count,
                    "last_aggregate_trade_id": state_item.get("last_aggregate_trade_id"),
                    "collector_state_updated_at": state_item.get("updated_at"),
                }
            )
            continue

        lag_seconds = max(0, int((now - latest_bar.close_time).total_seconds()))
        status = "ok"
        message = "Orderflow is fresh."
        if lag_seconds > max_staleness_seconds:
            status = "fail"
            message = f"Orderflow lag {lag_seconds}s exceeds {max_staleness_seconds}s."
        elif lag_seconds > max_staleness_seconds // 2:
            status = "warn"
            message = f"Orderflow lag {lag_seconds}s is elevated."
        elif recent_count == 0:
            status = "warn"
            message = f"No orderflow rows in the last {recent_window_minutes} minutes."

        rows.append(
            {
                "symbol": symbol,
                "status": status,
                "message": message,
                "latest_bar_open_time": latest_bar.open_time.isoformat(),
                "latest_bar_close_time": latest_bar.close_time.isoformat(),
                "lag_seconds": lag_seconds,
                "recent_bar_count": recent_count,
                "last_aggregate_trade_id": state_item.get("last_aggregate_trade_id"),
                "collector_state_updated_at": state_item.get("updated_at"),
            }
        )

    overall = "ok"
    if any(row["status"] == "fail" for row in rows):
        overall = "fail"
    elif any(row["status"] == "warn" for row in rows):
        overall = "warn"

    return {
        "status": overall,
        "generated_at": now.isoformat(),
        "interval": interval,
        "trading_mode": trading_mode,
        "max_staleness_seconds": max_staleness_seconds,
        "recent_window_minutes": recent_window_minutes,
        "state_path": state_path,
        "state_loaded": bool(state),
        "symbols": rows,
    }


def _load_state(state_path: str | None) -> dict[str, dict[str, Any]]:
    if not state_path:
        return {}
    path = Path(state_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text())
