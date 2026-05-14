from datetime import datetime, timedelta

from app.models import FundingRatePoint, OhlcvCandle, OpenInterestPoint, SignalType, StrategyFamily
from app.services.market_data import build_funding_crowding_fade_event
from app.services.researcher.mock_researcher import build_strategy_code


def _candles(count: int = 90) -> list[OhlcvCandle]:
    start = datetime(2026, 5, 1)
    candles = []
    for index in range(count):
        open_time = start + timedelta(minutes=5 * index)
        close = 100 + index * 0.05
        high = close + 0.4
        if index == count - 4:
            high = 110.0
        if index >= count - 3:
            high = 111.5
        if index == count - 1:
            close = 109.0
        candles.append(
            OhlcvCandle(
                symbol="BTC/USDT:USDT",
                interval="5m",
                open_time=open_time,
                close_time=open_time + timedelta(minutes=5),
                open=close - 0.2,
                high=high,
                low=close - 0.6,
                close=close,
                volume=100 + (200 if index == count - 1 else index),
                quote_volume=close * (100 + index),
                trade_count=100 + index,
                raw=[],
            )
        )
    return candles


def _funding_rates(count: int = 90) -> list[FundingRatePoint]:
    start = datetime(2026, 4, 1)
    rates = []
    for index in range(count):
        rate = 0.00005 + index * 0.000001
        if index == count - 1:
            rate = 0.0015
        rates.append(
            FundingRatePoint(
                symbol="BTC/USDT:USDT",
                funding_time=start + timedelta(hours=8 * index),
                funding_rate=rate,
                mark_price=None,
                raw={},
            )
        )
    return rates


def test_build_funding_crowding_event_from_ohlcv_and_funding() -> None:
    result = build_funding_crowding_fade_event(
        thesis_id="thesis_funding",
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        candles=_candles(),
        funding_rates=_funding_rates(),
        min_rank=60,
    )

    assert result.signal is not None
    assert result.event_episode is not None
    assert result.signal.signal_type == SignalType.FUNDING_OI_EXTREME
    assert result.signal.rank_score >= 60
    assert result.signal.features["funding_percentile_30d"] >= 90
    assert result.signal.features["failed_breakout_3bar"] is True
    assert result.event_episode.strategy_family == StrategyFamily.FUNDING_CROWDING_FADE
    assert "historical_open_interest" in result.event_episode.missing_evidence


def test_build_funding_crowding_event_uses_open_interest_when_provided() -> None:
    start = datetime(2026, 4, 1)
    oi = [
        OpenInterestPoint(
            symbol="BTC/USDT:USDT",
            timestamp=start + timedelta(hours=index),
            open_interest=1000 + index,
            raw={},
        )
        for index in range(90)
    ]

    result = build_funding_crowding_fade_event(
        thesis_id="thesis_funding",
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        candles=_candles(),
        funding_rates=_funding_rates(),
        open_interest_points=oi,
        min_rank=60,
    )

    assert result.signal is not None
    assert result.signal.features["open_interest_source"] == "historical_open_interest"
    assert result.missing_evidence == []


def test_funding_crowding_strategy_template_reads_funding_informative_data() -> None:
    code = build_strategy_code(
        strategy_name="FundingCrowdingFadeShort",
        timeframe="5m",
        template_name="funding_crowding_fade_short",
    )

    assert '@informative("1h", candle_type="funding_rate")' in code
    assert "funding_percentile_30d_1h" in code
    assert "open_interest_percentile_30d" in code
