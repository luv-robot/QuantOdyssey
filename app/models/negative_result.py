from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NegativeResultCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    thesis_id: str | None = None
    signal_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    failure_patterns: list[str] = Field(default_factory=list)
    reusable_lessons: list[str] = Field(default_factory=list)
    linked_artifacts: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
