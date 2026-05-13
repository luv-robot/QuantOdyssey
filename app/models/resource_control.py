from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResourceBudgetReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    estimated_monte_carlo_cost: int = Field(ge=0)
    max_allowed_cost: int = Field(ge=1)
    approved: bool
    requires_human_approval: bool
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
