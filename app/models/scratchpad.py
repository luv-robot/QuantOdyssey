from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScratchpadEventType(str, Enum):
    NOTE = "note"
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    RESEARCH_TASK = "research_task"
    BACKTEST_RESULT = "backtest_result"
    REVIEW_SESSION = "review_session"
    RESEARCH_FINDING = "research_finding"
    BUDGET_DECISION = "budget_decision"
    AGENT_EVAL_RESULT = "agent_eval_result"


class ResearchScratchpadEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    event_type: ScratchpadEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None
    thesis_id: str | None = None
    strategy_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchScratchpadRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    scratchpad_path: str = Field(min_length=1)
    event_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
