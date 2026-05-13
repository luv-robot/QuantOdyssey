from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import (
    MarketSignal,
    ReviewCase,
    ReviewResult,
    RiskAuditResult,
    StrategyManifest,
)


def sample_signal(rank_score: int = 82) -> MarketSignal:
    return MarketSignal(
        signal_id="signal_001",
        created_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="5m",
        signal_type="volume_spike",
        rank_score=rank_score,
        features={"volume_zscore": 3.1, "price_change_pct": 0.024},
        hypothesis="Volume spike may indicate continuation.",
        data_sources=["binance"],
    )


def sample_manifest() -> StrategyManifest:
    return StrategyManifest(
        strategy_id="strategy_001",
        signal_id="signal_001",
        name="VolumeSpikeTrendV1",
        file_path="freqtrade_user_data/strategies/VolumeSpikeTrendV1.py",
        generated_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
        timeframe="5m",
        symbols=["BTC/USDT"],
        assumptions=["Volume spike indicates continuation."],
        failure_modes=["Fails during fake breakouts."],
    )


def test_market_signal_rejects_invalid_rank_score() -> None:
    with pytest.raises(ValidationError):
        sample_signal(rank_score=101)


def test_market_signal_normalizes_exchange_and_symbol() -> None:
    signal = sample_signal()

    assert signal.exchange == "binance"
    assert signal.symbol == "BTC/USDT"


def test_strategy_name_must_be_identifier() -> None:
    payload = sample_manifest().model_dump()
    payload["name"] = "not-a-class"

    with pytest.raises(ValidationError):
        StrategyManifest(**payload)


def test_rejected_risk_audit_requires_findings() -> None:
    with pytest.raises(ValidationError):
        RiskAuditResult(strategy_id="strategy_001", approved=False, findings=[])


def test_failed_review_requires_failure_reason() -> None:
    with pytest.raises(ValidationError):
        ReviewCase(
            case_id="case_001",
            strategy_id="strategy_001",
            signal_id="signal_001",
            result=ReviewResult.FAILED,
            pattern="Low-quality signal failed.",
            avoid_conditions=["low trend strength"],
            reusable_lessons=["Require trend confirmation."],
        )
