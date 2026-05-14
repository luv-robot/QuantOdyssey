from datetime import datetime, timedelta

from app.flows import run_real_data_scout_flow
from app.models import DataQualityFlag
from app.services.market_data import BinanceMarketDataClient, clean_ohlcv, quality_check_market_dataset
from app.storage import QuantRepository


def fake_binance_transport(url: str):
    if "/api/v3/klines" in url:
        rows = []
        for index in range(60):
            volume = 100
            if index == 59:
                volume = 500
            open_price = 100 + index
            close_price = open_price + (3 if index == 59 else 1)
            rows.append(
                [
                    1710000000000 + index * 300000,
                    str(open_price),
                    str(close_price + 1),
                    str(open_price - 1),
                    str(close_price),
                    str(volume),
                    1710000299999 + index * 300000,
                    str(volume * close_price),
                    100 + index,
                    "0",
                    "0",
                    "0",
                ]
            )
        return rows

    if "/fapi/v1/fundingRate" in url:
        return [
            {
                "symbol": "BTCUSDT",
                "fundingRate": "0.0001",
                "fundingTime": 1710000000000,
                "markPrice": "101",
            }
        ]

    if "/fapi/v1/openInterest" in url:
        return {"symbol": "BTCUSDT", "openInterest": "12345.67", "time": 1710000000000}

    if "/futures/data/openInterestHist" in url:
        return [
            {
                "symbol": "BTCUSDT",
                "sumOpenInterest": "11111.1",
                "sumOpenInterestValue": "22222.2",
                "timestamp": 1710000000000,
            }
        ]

    if "/api/v3/depth" in url:
        return {
            "lastUpdateId": 123,
            "bids": [["159.9", "10"]],
            "asks": [["160.1", "12"]],
        }

    raise AssertionError(f"Unexpected URL: {url}")


def test_binance_client_parses_market_data() -> None:
    client = BinanceMarketDataClient(transport=fake_binance_transport)

    candles = client.fetch_ohlcv("BTC/USDT")
    funding = client.fetch_funding_rate("BTC/USDT")
    open_interest = client.fetch_open_interest("BTC/USDT")
    open_interest_history = client.fetch_open_interest_history("BTC/USDT")
    orderbook = client.fetch_orderbook("BTC/USDT")

    assert len(candles) == 60
    assert candles[-1].volume == 500
    assert funding[-1].funding_rate == 0.0001
    assert open_interest.open_interest == 12345.67
    assert open_interest_history[-1].open_interest == 11111.1
    assert orderbook.bids[0].price == 159.9


def test_quality_check_flags_missing_data() -> None:
    client = BinanceMarketDataClient(transport=fake_binance_transport)
    candles = client.fetch_ohlcv("BTC/USDT")[:10]

    report = quality_check_market_dataset("dataset", candles, expected_min_candles=50)

    assert report.is_usable is False
    assert DataQualityFlag.MISSING_DATA in report.flags


def test_quality_check_flags_stale_funding_and_open_interest() -> None:
    client = BinanceMarketDataClient(transport=fake_binance_transport)
    candles = client.fetch_ohlcv("BTC/USDT")
    funding = client.fetch_funding_rate("BTC/USDT")
    open_interest_history = client.fetch_open_interest_history("BTC/USDT")

    report = quality_check_market_dataset(
        "dataset",
        candles,
        funding_rates=funding,
        open_interest_points=open_interest_history,
        now=datetime(2024, 3, 15),
        stale_after=timedelta(days=1),
    )

    assert report.is_usable is False
    assert DataQualityFlag.STALE_DATA in report.flags


def test_clean_ohlcv_removes_extreme_outlier() -> None:
    client = BinanceMarketDataClient(transport=fake_binance_transport)
    candles = client.fetch_ohlcv("BTC/USDT")
    extreme = candles[-1].model_copy(update={"volume": 100000})

    cleaned = clean_ohlcv(candles[:-1] + [extreme], max_zscore=2)

    assert extreme not in cleaned


def test_real_data_scout_flow_persists_raw_data_quality_and_signal() -> None:
    repository = QuantRepository()
    client = BinanceMarketDataClient(transport=fake_binance_transport)

    result = run_real_data_scout_flow(
        symbol="BTC/USDT",
        interval="5m",
        min_rank=70,
        repository=repository,
        client=client,
    )

    assert result.quality_report.is_usable is True
    assert result.signal is not None
    assert repository.get_signal(result.signal.signal_id) == result.signal
    assert repository.get_ohlcv(f"{result.dataset_prefix}:ohlcv")
    assert repository.get_funding_rates(f"{result.dataset_prefix}:funding")
    assert repository.get_open_interest(f"{result.dataset_prefix}:open_interest") is not None
    assert repository.get_orderbook(f"{result.dataset_prefix}:orderbook") is not None
    assert repository.get_data_quality_report(result.dataset_prefix) == result.quality_report
