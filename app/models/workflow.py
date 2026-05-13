from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkflowState(str, Enum):
    NEW_SIGNAL = "NEW_SIGNAL"
    SIGNAL_VALIDATED = "SIGNAL_VALIDATED"
    STRATEGY_GENERATED = "STRATEGY_GENERATED"
    RISK_AUDITING = "RISK_AUDITING"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    BACKTEST_RUNNING = "BACKTEST_RUNNING"
    BACKTEST_PASSED = "BACKTEST_PASSED"
    BACKTEST_FAILED = "BACKTEST_FAILED"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    PAPER_TRADING = "PAPER_TRADING"
    PAPER_EVALUATION = "PAPER_EVALUATION"
    LIVE_CANDIDATE = "LIVE_CANDIDATE"
    RETIRED = "RETIRED"


class WorkflowRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_run_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    state: WorkflowState
    strategy_id: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None

    def transition(self, state: WorkflowState, error: Optional[str] = None) -> "WorkflowRun":
        return self.model_copy(update={"state": state, "updated_at": datetime.utcnow(), "error": error})
