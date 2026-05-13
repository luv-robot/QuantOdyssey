from __future__ import annotations

from datetime import datetime
from statistics import mean, pstdev

from app.models import FundingRatePoint, MarketSignal, OhlcvCandle, OpenInterestPoint, OrderBookSnapshot


def build_market_signal_from_dataset(
    symbol: str,
    candles: list[OhlcvCandle],
    funding_rates: list[FundingRatePoint],
    open_interest: OpenInterestPoint,
    orderbook: OrderBookSnapshot,
    min_rank: int = 70,
) -> MarketSignal | None:
    if len(candles) < 20:
        return None

    latest = candles[-1]
    historical_volumes = [candle.volume for candle in candles[:-1]]
    volume_stdev = pstdev(historical_volumes) or 1
    volume_zscore = (latest.volume - mean(historical_volumes)) / volume_stdev
    price_change_pct = (latest.close - candles[-2].close) / candles[-2].close
    funding_rate = funding_rates[-1].funding_rate if funding_rates else 0
    spread_pct = (orderbook.asks[0].price - orderbook.bids[0].price) / latest.close

    rank_score = _rank_score(volume_zscore, price_change_pct, funding_rate, spread_pct)
    if rank_score < min_rank:
        return None

    signal_type = "funding_oi_extreme" if abs(funding_rate) >= 0.001 else "volume_spike"
    return MarketSignal(
        signal_id=f"{symbol.replace('/', '').lower()}_{signal_type}_{int(datetime.utcnow().timestamp())}",
        created_at=datetime.utcnow(),
        market="crypto",
        exchange="binance",
        symbol=symbol,
        timeframe=latest.interval,
        signal_type=signal_type,
        rank_score=rank_score,
        features={
            "volume_zscore": round(volume_zscore, 4),
            "price_change_pct": round(price_change_pct, 6),
            "funding_rate": funding_rate,
            "open_interest": open_interest.open_interest,
            "spread_pct": round(spread_pct, 6),
            "latest_close": latest.close,
        },
        hypothesis="Real Binance market data indicates an actionable anomaly worth research.",
        data_sources=["binance_klines", "binance_funding_rate", "binance_open_interest", "binance_depth"],
    )


def _rank_score(
    volume_zscore: float,
    price_change_pct: float,
    funding_rate: float,
    spread_pct: float,
) -> int:
    score = 45
    score += min(30, max(0, int(volume_zscore * 8)))
    score += min(15, abs(int(price_change_pct * 500)))
    score += min(10, abs(int(funding_rate * 5000)))
    if spread_pct <= 0.001:
        score += 5
    return max(0, min(100, score))
