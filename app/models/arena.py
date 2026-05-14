from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ArenaScoreComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    score: float = Field(ge=0, le=100)
    weight: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)


class ArenaScoreReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    backtest_id: str = Field(min_length=1)
    scoring_version: str = Field(default="arena_v0.1")
    final_score: float = Field(ge=0, le=100)
    weighted_score: float = Field(ge=0, le=100)
    overfit_penalty: float = Field(ge=0, le=25)
    components: list[ArenaScoreComponent] = Field(min_length=1)
    public_metrics: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
