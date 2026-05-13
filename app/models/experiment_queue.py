from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExperimentQueueStatus(str, Enum):
    APPROVED = "approved"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class ExperimentQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue_id: str = Field(min_length=1)
    thesis_id: str | None = None
    signal_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    status: ExperimentQueueStatus
    reason: str = Field(min_length=1)
    estimated_cost: int = Field(ge=0)
    approved_by: str | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
