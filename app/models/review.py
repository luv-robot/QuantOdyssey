from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    RISK_REJECTED = "risk_rejected"


class ReviewCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    result: ReviewResult
    pattern: str = Field(min_length=1)
    failure_reason: Optional[str] = None
    avoid_conditions: list[str]
    reusable_lessons: list[str] = Field(min_length=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def failed_cases_need_reason(self) -> "ReviewCase":
        if self.result in {ReviewResult.FAILED, ReviewResult.RISK_REJECTED} and not self.failure_reason:
            raise ValueError("failed or risk-rejected reviews must include failure_reason")
        return self
