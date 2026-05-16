from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BacktestCostModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fee_rate: float = Field(default=0.0005, ge=0, le=0.1)
    slippage_bps: float = Field(default=2.0, ge=0)
    spread_bps: float = Field(default=0.0, ge=0)
    funding_rate_8h: float = 0.0
    funding_source: str = Field(default="not_available", min_length=1)
    notes: list[str] = Field(default_factory=list)

