import json
from datetime import datetime

from app.services.market_data.freqtrade_files import (
    find_freqtrade_funding_file,
    find_open_interest_file,
    load_open_interest_points,
)


def test_load_open_interest_points_from_json(tmp_path) -> None:
    path = tmp_path / "BTC_USDT_USDT-5m-open_interest.json"
    path.write_text(
        json.dumps(
            [
                {
                    "symbol": "BTCUSDT",
                    "timestamp": "2026-05-01T00:00:00+00:00",
                    "open_interest": 12345.6,
                }
            ]
        ),
        encoding="utf-8",
    )

    points = load_open_interest_points(path, "BTC/USDT:USDT")

    assert points[0].symbol == "BTC/USDT:USDT"
    assert points[0].timestamp == datetime(2026, 5, 1)
    assert points[0].timestamp.tzinfo is None
    assert points[0].open_interest == 12345.6


def test_find_auxiliary_files_next_to_futures_ohlcv(tmp_path) -> None:
    ohlcv = tmp_path / "BTC_USDT_USDT-5m-futures.feather"
    funding = tmp_path / "BTC_USDT_USDT-1h-funding_rate.feather"
    oi = tmp_path / "BTC_USDT_USDT-5m-open_interest.json"
    ohlcv.touch()
    funding.touch()
    oi.touch()

    assert find_freqtrade_funding_file(ohlcv, "BTC/USDT:USDT", "5m") == funding
    assert find_open_interest_file(ohlcv, "BTC/USDT:USDT", "5m") == oi
