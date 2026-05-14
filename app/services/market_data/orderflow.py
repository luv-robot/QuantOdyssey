from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import AggregateTrade, OrderflowBar


def build_orderflow_bars(
    trades: list[AggregateTrade],
    *,
    interval: str = "1m",
    start_cvd: float = 0.0,
) -> list[OrderflowBar]:
    """Aggregate Binance aggTrades into taker-flow bars with cumulative volume delta."""
    if not trades:
        return []
    seconds = _interval_seconds(interval)
    grouped: dict[datetime, list[AggregateTrade]] = {}
    for trade in sorted(trades, key=lambda item: item.timestamp):
        bucket = _floor_time(trade.timestamp, seconds)
        grouped.setdefault(bucket, []).append(trade)

    cvd = start_cvd
    bars: list[OrderflowBar] = []
    for open_time in sorted(grouped):
        bucket_trades = grouped[open_time]
        buy_volume = sum(trade.quantity for trade in bucket_trades if not trade.buyer_is_maker)
        sell_volume = sum(trade.quantity for trade in bucket_trades if trade.buyer_is_maker)
        buy_quote = sum(trade.quantity * trade.price for trade in bucket_trades if not trade.buyer_is_maker)
        sell_quote = sum(trade.quantity * trade.price for trade in bucket_trades if trade.buyer_is_maker)
        net_volume = buy_volume - sell_volume
        net_quote = buy_quote - sell_quote
        total_volume = buy_volume + sell_volume
        total_quote = buy_quote + sell_quote
        cvd += net_volume
        bars.append(
            OrderflowBar(
                symbol=bucket_trades[0].symbol,
                interval=interval,
                open_time=open_time,
                close_time=open_time + timedelta(seconds=seconds),
                buy_volume=round(buy_volume, 8),
                sell_volume=round(sell_volume, 8),
                buy_quote_volume=round(buy_quote, 8),
                sell_quote_volume=round(sell_quote, 8),
                net_taker_volume=round(net_volume, 8),
                net_taker_quote_volume=round(net_quote, 8),
                cumulative_volume_delta=round(cvd, 8),
                taker_buy_ratio=round(buy_volume / total_volume, 8) if total_volume else 0.0,
                trade_count=sum(max(1, trade.last_trade_id - trade.first_trade_id + 1) for trade in bucket_trades),
                vwap=round(total_quote / total_volume, 8) if total_volume else None,
            )
        )
    return bars


def _interval_seconds(interval: str) -> int:
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == "s":
        return max(1, value)
    if unit == "m":
        return max(1, value * 60)
    if unit == "h":
        return max(1, value * 3600)
    raise ValueError(f"Unsupported orderflow interval: {interval}")


def _floor_time(value: datetime, seconds: int) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    epoch = int(value.timestamp())
    floored = epoch - (epoch % seconds)
    return datetime.utcfromtimestamp(floored)
