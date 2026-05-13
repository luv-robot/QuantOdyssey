from __future__ import annotations

from datetime import datetime

from app.models import MarketSignal


def generate_volume_spike_signal(
    signal_id: str = "signal_volume_spike_001",
    symbol: str = "BTC/USDT",
    rank_score: int = 82,
) -> MarketSignal:
    return MarketSignal(
        signal_id=signal_id,
        created_at=datetime.utcnow(),
        market="crypto",
        exchange="binance",
        symbol=symbol,
        timeframe="5m",
        signal_type="volume_spike",
        rank_score=rank_score,
        features={"volume_zscore": 3.1, "price_change_pct": 0.024},
        hypothesis="Volume spike may indicate short-term continuation.",
        data_sources=["binance"],
    )


def generate_funding_oi_extreme_signal(
    signal_id: str = "signal_funding_oi_001",
    symbol: str = "ETH/USDT",
    rank_score: int = 78,
) -> MarketSignal:
    return MarketSignal(
        signal_id=signal_id,
        created_at=datetime.utcnow(),
        market="crypto",
        exchange="binance",
        symbol=symbol,
        timeframe="15m",
        signal_type="funding_oi_extreme",
        rank_score=rank_score,
        features={"funding_rate": 0.0012, "open_interest_zscore": 2.7},
        hypothesis="Funding and open-interest extremes may indicate crowded positioning.",
        data_sources=["binance", "coinglass"],
    )


def filter_ranked_signals(signals: list[MarketSignal], min_rank: int = 70) -> list[MarketSignal]:
    return [signal for signal in signals if signal.rank_score >= min_rank]
