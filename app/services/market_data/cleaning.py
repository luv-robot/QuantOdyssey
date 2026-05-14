from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean, pstdev

from app.models import (
    DataQualityFlag,
    DataQualityReport,
    FundingRatePoint,
    OhlcvCandle,
    OpenInterestPoint,
    OrderBookSnapshot,
)


def clean_ohlcv(candles: list[OhlcvCandle], max_zscore: float = 8.0) -> list[OhlcvCandle]:
    if len(candles) < 3:
        return candles

    volumes = [candle.volume for candle in candles]
    avg = mean(volumes)
    stdev = pstdev(volumes) or 1
    return [candle for candle in candles if abs((candle.volume - avg) / stdev) <= max_zscore]


def quality_check_market_dataset(
    dataset_id: str,
    candles: list[OhlcvCandle],
    orderbook: OrderBookSnapshot | None = None,
    funding_rates: list[FundingRatePoint] | None = None,
    open_interest_points: list[OpenInterestPoint] | None = None,
    expected_min_candles: int = 50,
    now: datetime | None = None,
    stale_after: timedelta = timedelta(days=2),
) -> DataQualityReport:
    flags: list[DataQualityFlag] = []
    details: list[str] = []

    if len(candles) < expected_min_candles:
        flags.append(DataQualityFlag.MISSING_DATA)
        details.append(f"Expected at least {expected_min_candles} candles, got {len(candles)}.")

    if any(candle.close <= 0 for candle in candles):
        flags.append(DataQualityFlag.NON_POSITIVE_PRICE)
        details.append("At least one candle has a non-positive close price.")

    if any(candle.volume <= 0 for candle in candles):
        flags.append(DataQualityFlag.NON_POSITIVE_VOLUME)
        details.append("At least one candle has non-positive volume.")

    if orderbook is not None and (not orderbook.bids or not orderbook.asks):
        flags.append(DataQualityFlag.INVALID_ORDERBOOK)
        details.append("Orderbook is missing bid or ask side.")

    if funding_rates is not None:
        if not funding_rates:
            flags.append(DataQualityFlag.MISSING_DATA)
            details.append("Funding rate data was requested but no points were available.")
        elif now is not None and _is_stale(funding_rates[-1].funding_time, now, stale_after):
            flags.append(DataQualityFlag.STALE_DATA)
            details.append("Latest funding rate point is stale.")

    if open_interest_points is not None:
        if not open_interest_points:
            flags.append(DataQualityFlag.MISSING_DATA)
            details.append("Open interest data was requested but no points were available.")
        elif now is not None and _is_stale(open_interest_points[-1].timestamp, now, stale_after):
            flags.append(DataQualityFlag.STALE_DATA)
            details.append("Latest open interest point is stale.")

    return DataQualityReport(
        dataset_id=dataset_id,
        is_usable=not flags,
        flags=flags,
        details=details,
    )


def _is_stale(timestamp: datetime, now: datetime, stale_after: timedelta) -> bool:
    if timestamp.tzinfo is not None and now.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=None)
    if timestamp.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    return now - timestamp > stale_after
