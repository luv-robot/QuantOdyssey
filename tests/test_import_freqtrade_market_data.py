from datetime import datetime, timezone

from scripts.import_freqtrade_market_data import _row_to_candle


class FakeTimestamp:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def to_pydatetime(self) -> datetime:
        return self.value


def test_row_to_candle_maps_freqtrade_ohlcv_without_optional_columns() -> None:
    candle = _row_to_candle(
        {
            "date": FakeTimestamp(datetime(2026, 5, 10, tzinfo=timezone.utc)),
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
            "volume": 2.0,
        },
        "BTC/USDT",
        "5m",
    )

    assert candle.symbol == "BTC/USDT"
    assert candle.interval == "5m"
    assert candle.quote_volume == 210.0
    assert candle.trade_count == 0
    assert candle.close_time.minute == 5
