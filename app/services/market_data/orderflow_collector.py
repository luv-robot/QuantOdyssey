from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import AggregateTrade
from app.services.market_data.binance_client import BinanceMarketDataClient
from app.services.market_data.orderflow import build_orderflow_bars


OrderflowCollectorState = dict[str, dict[str, Any]]


def collect_symbol_orderflow_once(
    *,
    symbol: str,
    trading_mode: str,
    client: BinanceMarketDataClient,
    repository: Any,
    state: OrderflowCollectorState,
    limit: int = 1000,
    max_pages: int = 3,
    bar_interval: str = "1m",
    dataset_namespace: str = "binance",
) -> dict[str, Any]:
    """Fetch incremental Binance aggTrades for one symbol and persist raw/orderflow datasets."""
    key = _state_key(symbol, trading_mode)
    previous = state.get(key, {})
    previous_trade_id = previous.get("last_aggregate_trade_id")
    previous_cvd = float(previous.get("last_cumulative_volume_delta", 0.0))

    trades = _fetch_incremental_trades(
        client=client,
        symbol=symbol,
        trading_mode=trading_mode,
        previous_trade_id=previous_trade_id,
        limit=limit,
        max_pages=max_pages,
    )
    if not trades:
        return {
            "symbol": symbol,
            "trading_mode": trading_mode,
            "status": "no_new_trades",
            "trade_count": 0,
            "bar_count": 0,
            "last_aggregate_trade_id": previous_trade_id,
        }

    bars = build_orderflow_bars(trades, interval=bar_interval, start_cvd=previous_cvd)
    first_trade = trades[0]
    last_trade = trades[-1]
    dataset_prefix = (
        f"{dataset_namespace}:{trading_mode}:agg_trades:{_safe_symbol(symbol)}:"
        f"{first_trade.aggregate_trade_id}-{last_trade.aggregate_trade_id}:"
        f"{first_trade.timestamp.strftime('%Y%m%d%H%M%S')}-{last_trade.timestamp.strftime('%Y%m%d%H%M%S')}"
    )

    repository.save_aggregate_trades(f"{dataset_prefix}:raw", symbol, trades)
    repository.save_orderflow_bars(f"{dataset_prefix}:orderflow:{bar_interval}", symbol, bars)

    state[key] = {
        "symbol": symbol,
        "trading_mode": trading_mode,
        "last_aggregate_trade_id": last_trade.aggregate_trade_id,
        "last_trade_time": last_trade.timestamp.isoformat(),
        "last_cumulative_volume_delta": None if not bars else bars[-1].cumulative_volume_delta,
        "updated_at": datetime.utcnow().isoformat(),
    }
    return {
        "symbol": symbol,
        "trading_mode": trading_mode,
        "status": "saved",
        "trade_count": len(trades),
        "bar_count": len(bars),
        "raw_dataset_id": f"{dataset_prefix}:raw",
        "orderflow_dataset_id": f"{dataset_prefix}:orderflow:{bar_interval}",
        "first_aggregate_trade_id": first_trade.aggregate_trade_id,
        "last_aggregate_trade_id": last_trade.aggregate_trade_id,
        "first_trade_time": first_trade.timestamp.isoformat(),
        "last_trade_time": last_trade.timestamp.isoformat(),
    }


def _fetch_incremental_trades(
    *,
    client: BinanceMarketDataClient,
    symbol: str,
    trading_mode: str,
    previous_trade_id: int | None,
    limit: int,
    max_pages: int,
) -> list[AggregateTrade]:
    all_trades: list[AggregateTrade] = []
    from_id = previous_trade_id + 1 if previous_trade_id is not None else None
    for _ in range(max(1, max_pages)):
        trades = client.fetch_aggregate_trades(
            symbol,
            limit=limit,
            trading_mode=trading_mode,
            from_id=from_id,
        )
        if previous_trade_id is not None:
            trades = [trade for trade in trades if trade.aggregate_trade_id > previous_trade_id]
        if not trades:
            break
        all_trades.extend(trades)
        from_id = trades[-1].aggregate_trade_id + 1
        if len(trades) < limit:
            break
    return sorted(all_trades, key=lambda trade: trade.aggregate_trade_id)


def _state_key(symbol: str, trading_mode: str) -> str:
    return f"{trading_mode}:{symbol.upper()}"


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_").lower()
