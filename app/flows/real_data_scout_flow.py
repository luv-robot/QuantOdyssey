from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.models import DataQualityReport, MarketSignal
from app.services.market_data import (
    BinanceMarketDataClient,
    build_market_signal_from_dataset,
    clean_ohlcv,
    quality_check_market_dataset,
)
from app.storage import QuantRepository


@dataclass(frozen=True)
class RealDataScoutResult:
    signal: Optional[MarketSignal]
    quality_report: DataQualityReport
    dataset_prefix: str


def run_real_data_scout_flow(
    symbol: str = "BTC/USDT",
    interval: str = "5m",
    min_rank: int = 70,
    repository: Optional[QuantRepository] = None,
    client: Optional[BinanceMarketDataClient] = None,
) -> RealDataScoutResult:
    market_client = client or BinanceMarketDataClient()
    dataset_prefix = f"binance:{symbol}:{interval}"

    candles = clean_ohlcv(market_client.fetch_ohlcv(symbol, interval=interval))
    funding_rates = market_client.fetch_funding_rate(symbol)
    open_interest = market_client.fetch_open_interest(symbol)
    orderbook = market_client.fetch_orderbook(symbol)
    quality = quality_check_market_dataset(dataset_prefix, candles, orderbook=orderbook)

    if repository is not None:
        repository.save_ohlcv(f"{dataset_prefix}:ohlcv", symbol, candles)
        repository.save_funding_rates(f"{dataset_prefix}:funding", symbol, funding_rates)
        repository.save_open_interest(f"{dataset_prefix}:open_interest", symbol, open_interest)
        repository.save_orderbook(f"{dataset_prefix}:orderbook", symbol, orderbook)
        repository.save_data_quality_report(quality)

    signal = None
    if quality.is_usable:
        signal = build_market_signal_from_dataset(
            symbol=symbol,
            candles=candles,
            funding_rates=funding_rates,
            open_interest=open_interest,
            orderbook=orderbook,
            min_rank=min_rank,
        )
        if signal is not None and repository is not None:
            repository.save_signal(signal)

    return RealDataScoutResult(signal=signal, quality_report=quality, dataset_prefix=dataset_prefix)
