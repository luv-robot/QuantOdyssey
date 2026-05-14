from __future__ import annotations

from datetime import datetime
from statistics import mean, pstdev
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.models import (
    DataSufficiencyLevel,
    EvaluationType,
    EventEpisode,
    EventEpisodeStage,
    FundingRatePoint,
    MarketSignal,
    OhlcvCandle,
    OpenInterestPoint,
    SignalType,
    StrategyFamily,
)


class FundingCrowdingEventResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: MarketSignal | None
    event_episode: EventEpisode | None
    event_count: int
    trigger_count: int
    missing_evidence: list[str]
    details: list[str]


def build_funding_crowding_fade_event(
    *,
    thesis_id: str,
    symbol: str,
    timeframe: str,
    candles: list[OhlcvCandle],
    funding_rates: list[FundingRatePoint],
    open_interest_points: list[OpenInterestPoint] | None = None,
    min_rank: int = 60,
) -> FundingCrowdingEventResult:
    details: list[str] = []
    missing_evidence: list[str] = []
    if len(candles) < 64:
        return _empty_result(["At least 64 OHLCV candles are required for failed-breakout features."])
    if len(funding_rates) < 30:
        return _empty_result(["At least 30 funding-rate points are required for crowding percentiles."])

    sorted_candles = sorted(candles, key=lambda item: item.open_time)
    sorted_funding = sorted(funding_rates, key=lambda item: item.funding_time)
    latest = sorted_candles[-1]
    funding_percentile = _latest_percentile(
        [point.funding_rate for point in sorted_funding[-90:]],
        sorted_funding[-1].funding_rate,
    )
    bars_24h = _bars_for_duration(timeframe, hours=24)
    price_change_24h = _price_change(sorted_candles, bars_24h)
    vwap = _vwap(sorted_candles[-min(len(sorted_candles), 288):])
    price_distance_from_vwap = latest.close / vwap - 1 if vwap > 0 else 0
    volume_zscore = _zscore([candle.volume for candle in sorted_candles[-49:-1]], latest.volume)
    range_high = max(candle.high for candle in sorted_candles[-51:-3])
    recent_high_3 = max(candle.high for candle in sorted_candles[-3:])
    failed_breakout_3bar = recent_high_3 > range_high and latest.close < range_high
    oi_percentile, oi_source = _open_interest_percentile(open_interest_points, sorted_candles)
    if oi_source == "volume_proxy":
        missing_evidence.append("historical_open_interest")
        details.append("Open-interest percentile uses volume proxy until historical OI is imported into backtests.")

    setup_score = _setup_score(
        funding_percentile=funding_percentile,
        oi_percentile=oi_percentile,
        price_change_24h=price_change_24h,
        price_distance_from_vwap=price_distance_from_vwap,
        volume_zscore=volume_zscore,
    )
    trigger_score = _trigger_score(failed_breakout_3bar, price_distance_from_vwap, volume_zscore)
    rank_score = int(round(min(100, setup_score * 0.65 + trigger_score * 0.35)))
    event_count = _count_setup_events(sorted_candles, sorted_funding)
    trigger_count = 1 if failed_breakout_3bar else 0
    if rank_score < min_rank:
        return FundingCrowdingEventResult(
            signal=None,
            event_episode=None,
            event_count=event_count,
            trigger_count=trigger_count,
            missing_evidence=missing_evidence,
            details=details + [f"Rank score {rank_score} is below minimum {min_rank}."],
        )

    signal_id = f"signal_funding_crowding_{_safe_symbol(symbol)}_{latest.close_time:%Y%m%d%H%M%S}_{uuid4().hex[:6]}"
    features = {
        "funding_rate": round(sorted_funding[-1].funding_rate, 8),
        "funding_percentile_30d": round(funding_percentile, 2),
        "open_interest_percentile_30d": round(oi_percentile, 2),
        "open_interest_source": oi_source,
        "price_change_24h": round(price_change_24h, 6),
        "price_distance_from_vwap": round(price_distance_from_vwap, 6),
        "volume_zscore": round(volume_zscore, 4),
        "failed_breakout_3bar": failed_breakout_3bar,
        "setup_score": round(setup_score, 2),
        "trigger_score": round(trigger_score, 2),
        "event_count": event_count,
        "trigger_count": trigger_count,
    }
    signal = MarketSignal(
        signal_id=signal_id,
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol=symbol,
        timeframe=timeframe,
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=rank_score,
        features=features,
        hypothesis=(
            "Positive funding crowding plus elevated participation and failed upside extension "
            "may precede crowded-long exits."
        ),
        data_sources=[
            f"freqtrade:futures_ohlcv:{symbol}:{timeframe}",
            f"freqtrade:futures_funding_rate:{symbol}:1h",
            f"open_interest:{oi_source}",
        ],
    )
    event = EventEpisode(
        event_id=f"event_{thesis_id}_{signal_id}_{uuid4().hex[:8]}",
        thesis_id=thesis_id,
        signal_id=signal.signal_id,
        strategy_family=StrategyFamily.FUNDING_CROWDING_FADE,
        evaluation_type=EvaluationType.EVENT_DRIVEN_ALPHA,
        stage=EventEpisodeStage.SETUP,
        direction="short",
        symbol=symbol,
        timeframe=timeframe,
        setup_window_bars=min(288, len(sorted_candles)),
        trigger_window_bars=3,
        data_sufficiency_level=DataSufficiencyLevel.L1_FUNDING_OI,
        validation_data_sufficiency_level=(
            DataSufficiencyLevel.L0_OHLCV_ONLY if missing_evidence else DataSufficiencyLevel.L1_FUNDING_OI
        ),
        trigger_definition=(
            "funding_percentile_30d >= 90, open_interest_percentile_30d >= 75, "
            "24h price change positive, and a 3-bar failed breakout above the prior range high."
        ),
        features=features,
        missing_evidence=missing_evidence,
    )
    return FundingCrowdingEventResult(
        signal=signal,
        event_episode=event,
        event_count=event_count,
        trigger_count=trigger_count,
        missing_evidence=missing_evidence,
        details=details or ["Funding crowding event features were generated from traceable market data."],
    )


def _empty_result(details: list[str]) -> FundingCrowdingEventResult:
    return FundingCrowdingEventResult(
        signal=None,
        event_episode=None,
        event_count=0,
        trigger_count=0,
        missing_evidence=["insufficient_market_data"],
        details=details,
    )


def _latest_percentile(values: list[float], latest: float) -> float:
    if not values:
        return 50.0
    below_or_equal = sum(1 for value in values if value <= latest)
    return below_or_equal / len(values) * 100


def _price_change(candles: list[OhlcvCandle], bars: int) -> float:
    if len(candles) <= bars:
        return 0.0
    base = candles[-bars - 1].close
    return candles[-1].close / base - 1


def _vwap(candles: list[OhlcvCandle]) -> float:
    quote_volume = sum(candle.close * candle.volume for candle in candles)
    volume = sum(candle.volume for candle in candles)
    return quote_volume / volume if volume > 0 else candles[-1].close


def _zscore(history: list[float], latest: float) -> float:
    if not history:
        return 0.0
    stdev = pstdev(history) or 1
    return (latest - mean(history)) / stdev


def _open_interest_percentile(
    points: list[OpenInterestPoint] | None,
    candles: list[OhlcvCandle],
) -> tuple[float, str]:
    if points and len(points) >= 3:
        sorted_points = sorted(points, key=lambda item: item.timestamp)
        latest = sorted_points[-1].open_interest
        return _latest_percentile([point.open_interest for point in sorted_points[-90:]], latest), "historical_open_interest"
    volumes = [candle.volume for candle in candles[-90:]]
    return _latest_percentile(volumes, candles[-1].volume), "volume_proxy"


def _setup_score(
    funding_percentile: float,
    oi_percentile: float,
    price_change_24h: float,
    price_distance_from_vwap: float,
    volume_zscore: float,
) -> float:
    score = 20
    score += max(0, funding_percentile - 70) * 0.9
    score += max(0, oi_percentile - 55) * 0.55
    score += min(15, max(0, price_change_24h) * 250)
    score += min(12, max(0, price_distance_from_vwap) * 400)
    score += min(10, max(0, volume_zscore) * 5)
    return min(100, score)


def _trigger_score(failed_breakout_3bar: bool, price_distance_from_vwap: float, volume_zscore: float) -> float:
    score = 15
    if failed_breakout_3bar:
        score += 55
    score += min(15, max(0, price_distance_from_vwap) * 500)
    score += min(15, max(0, volume_zscore) * 6)
    return min(100, score)


def _count_setup_events(candles: list[OhlcvCandle], funding_rates: list[FundingRatePoint]) -> int:
    if len(candles) < 64 or len(funding_rates) < 30:
        return 0
    funding_threshold = sorted(point.funding_rate for point in funding_rates)[int(len(funding_rates) * 0.8)]
    count = 0
    for index in range(64, len(candles)):
        price_change = candles[index].close / candles[max(0, index - 288)].close - 1
        if funding_rates[-1].funding_rate >= funding_threshold and price_change > 0:
            count += 1
    return count


def _bars_for_duration(timeframe: str, hours: int) -> int:
    unit = timeframe[-1]
    value = int(timeframe[:-1])
    if unit == "m":
        return max(1, hours * 60 // value)
    if unit == "h":
        return max(1, hours // value)
    return 1


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_").lower()
