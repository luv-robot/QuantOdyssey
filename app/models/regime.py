from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.trade import MarketRegime


class MarketRegimeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regime_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    primary_regime: MarketRegime
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    feature_snapshot: dict[str, float | int | str | bool] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
