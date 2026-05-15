from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AgentEvalTarget(str, Enum):
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    HARNESS = "harness"
    RISK_AUDITOR = "risk_auditor"
    SUPERVISOR = "supervisor"


class AgentEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    target_agent: AgentEvalTarget
    title: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    input_artifacts: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    expected_terms: list[str] = Field(default_factory=list)
    prohibited_terms: list[str] = Field(default_factory=list)
    rubric: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentEvalCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    target_agent: AgentEvalTarget
    passed: bool
    score: float = Field(ge=0, le=100)
    missing_expectations: list[str] = Field(default_factory=list)
    unexpected_claims: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    response_excerpt: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentEvalRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    suite_version: str = Field(min_length=1)
    results: list[AgentEvalCaseResult] = Field(default_factory=list)
    aggregate_scores: dict[str, float] = Field(default_factory=dict)
    passed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
