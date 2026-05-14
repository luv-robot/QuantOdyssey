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


class ReviewClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    severity: str = Field(default="medium", min_length=1)


class ReviewQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    user_response: Optional[str] = None


class ResearchMaturityScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_score: float = Field(ge=0, le=100)
    thesis_clarity: float = Field(ge=0, le=100)
    data_sufficiency: float = Field(ge=0, le=100)
    sample_maturity: float = Field(ge=0, le=100)
    baseline_advantage: float = Field(ge=0, le=100)
    robustness: float = Field(ge=0, le=100)
    regime_stability: float = Field(ge=0, le=100)
    failure_understanding: float = Field(ge=0, le=100)
    implementation_safety: float = Field(ge=0, le=100)
    overfit_risk: float = Field(ge=0, le=100)
    stage: str = Field(min_length=1)
    blockers: list[str] = Field(default_factory=list)


class ReviewSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    thesis_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    review_case_id: Optional[str] = None
    scorecard: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    evidence_for: list[ReviewClaim] = Field(default_factory=list)
    evidence_against: list[ReviewClaim] = Field(default_factory=list)
    blind_spots: list[ReviewClaim] = Field(default_factory=list)
    ai_questions: list[ReviewQuestion] = Field(default_factory=list)
    next_experiments: list[str] = Field(default_factory=list)
    user_responses: list[str] = Field(default_factory=list)
    maturity_score: ResearchMaturityScore
    created_at: datetime = Field(default_factory=datetime.utcnow)
