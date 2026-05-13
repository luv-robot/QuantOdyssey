from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RobustnessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    source_backtest_id: str = Field(min_length=1)
    baseline_report_id: str = Field(min_length=1)
    monte_carlo_report_id: str = Field(min_length=1)
    validation_id: str = Field(min_length=1)
    statistical_confidence_score: float = Field(ge=0, le=100)
    robustness_score: float = Field(ge=0, le=100)
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
