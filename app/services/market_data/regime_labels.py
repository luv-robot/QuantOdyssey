from __future__ import annotations

from app.models import MarketRegime, MarketRegimeSnapshot, MarketSignal


def label_market_regime(signal: MarketSignal) -> MarketRegimeSnapshot:
    features = signal.features
    funding_rate = float(features.get("funding_rate", 0) or 0)
    volatility = float(features.get("volatility", features.get("volatility_pct", 0)) or 0)
    price_change = float(features.get("price_change_pct", features.get("return_pct", 0)) or 0)
    volume_zscore = float(features.get("volume_zscore", 0) or 0)
    liquidity_score = float(features.get("liquidity_score", 1) or 1)

    reasons: list[str] = []
    regime = MarketRegime.RANGING
    confidence = 0.55

    if abs(funding_rate) >= 0.001:
        regime = MarketRegime.FUNDING_EXTREME
        confidence = min(0.95, 0.65 + abs(funding_rate) * 100)
        reasons.append("Funding rate is extreme relative to the default threshold.")
    elif liquidity_score <= 0.2:
        regime = MarketRegime.LOW_LIQUIDITY
        confidence = 0.75
        reasons.append("Liquidity score is low.")
    elif volatility >= 0.03:
        regime = MarketRegime.HIGH_VOLATILITY
        confidence = min(0.9, 0.6 + volatility * 5)
        reasons.append("Recent volatility is elevated.")
    elif price_change <= -0.05:
        regime = MarketRegime.MARKET_SYNC_DOWN
        confidence = 0.75
        reasons.append("Signal window price change is sharply negative.")
    elif abs(price_change) >= 0.03 or volume_zscore >= 2.5:
        regime = MarketRegime.TRENDING
        confidence = 0.7 if abs(price_change) >= 0.03 else 0.62
        reasons.append("Price change or relative volume suggests trend continuation.")
    else:
        reasons.append("No extreme funding, liquidity, volatility, or trend feature was detected.")

    return MarketRegimeSnapshot(
        regime_id=f"regime_{signal.signal_id}",
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        primary_regime=regime,
        confidence=round(confidence, 4),
        reasons=reasons,
        feature_snapshot=dict(features),
    )
