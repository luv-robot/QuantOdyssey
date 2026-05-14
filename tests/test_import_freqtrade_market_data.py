from datetime import datetime, timezone

from scripts.import_freqtrade_market_data import _row_to_candle, _row_to_funding_rate


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


def test_row_to_funding_rate_maps_freqtrade_funding_file_shape() -> None:
    point = _row_to_funding_rate(
        {
            "date": FakeTimestamp(datetime(2026, 5, 10, tzinfo=timezone.utc)),
            "open": 0.000123,
            "high": 0.0,
            "low": 0.0,
            "close": 0.0,
            "volume": 0.0,
        },
        "BTC/USDT:USDT",
    )

    assert point.symbol == "BTC/USDT:USDT"
    assert point.funding_rate == 0.000123
    assert point.raw["source"] == "freqtrade_funding_rate_feather"
