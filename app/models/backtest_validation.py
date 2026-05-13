from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BacktestValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    walk_forward_passed: bool
    out_of_sample_passed: bool
    sensitivity_passed: bool
    fee_slippage_passed: bool
    minimum_trades_passed: bool
    overfitting_detected: bool
    quality_score: float = Field(default=0, ge=0, le=100)
    quality_passed: bool = False
    quality_metrics: dict[str, float] = Field(default_factory=dict)
    approved: bool
    findings: list[str]
