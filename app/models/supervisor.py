from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SupervisorStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    CRITICAL = "critical"


class SupervisorFlagSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class SupervisorFlagKind(str, Enum):
    AGENT_EVAL_FAILURE = "agent_eval_failure"
    REVIEW_SESSION_RISK = "review_session_risk"
    TASK_BUDGET_RISK = "task_budget_risk"
    DATA_GAP = "data_gap"
    SYSTEM_NOTE = "system_note"


class SupervisorFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag_id: str = Field(min_length=1)
    kind: SupervisorFlagKind
    severity: SupervisorFlagSeverity
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    linked_agent_eval_run_id: str | None = None
    linked_review_session_id: str | None = None
    linked_task_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SupervisorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    source_agent_eval_run_id: str | None = None
    status: SupervisorStatus
    summary: str = Field(min_length=1)
    aggregate_scores: dict[str, float] = Field(default_factory=dict)
    flags: list[SupervisorFlag] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
