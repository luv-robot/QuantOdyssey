from __future__ import annotations

from statistics import mean, pstdev

from app.models import DataQualityFlag, DataQualityReport, OhlcvCandle, OrderBookSnapshot


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
    expected_min_candles: int = 50,
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

    return DataQualityReport(
        dataset_id=dataset_id,
        is_usable=not flags,
        flags=flags,
        details=details,
    )
