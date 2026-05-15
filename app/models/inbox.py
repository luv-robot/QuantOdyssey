from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.research import DataSufficiencyLevel, StrategyFamily


class ThesisInboxSource(str, Enum):
    HUMAN_SEEDED = "human_seeded"
    BASELINE_DERIVED = "baseline_derived"
    REGIME_DERIVED = "regime_derived"
    FAILURE_DERIVED = "failure_derived"
    REVIEW_SESSION_DERIVED = "review_session_derived"
    DATA_GAP_DERIVED = "data_gap_derived"
    WATCHLIST_DERIVED = "watchlist_derived"
    MACHINE_SEEDED = "machine_seeded"


class ThesisInboxStatus(str, Enum):
    SUGGESTED = "suggested"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    CONVERTED_TO_THESIS = "converted_to_thesis"
    CONVERTED_TO_TASK = "converted_to_task"


class ThesisInboxItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    source: ThesisInboxSource
    status: ThesisInboxStatus = ThesisInboxStatus.SUGGESTED
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    proposed_observation: str = Field(min_length=1)
    proposed_hypothesis: str = Field(min_length=1)
    proposed_trade_logic: str = Field(min_length=1)
    suggested_questions: list[str] = Field(default_factory=list)
    suggested_experiments: list[str] = Field(default_factory=list)
    suggested_success_metrics: list[str] = Field(default_factory=list)
    suggested_failure_conditions: list[str] = Field(default_factory=list)
    strategy_family: StrategyFamily = StrategyFamily.GENERAL_OR_UNKNOWN
    required_data_level: DataSufficiencyLevel = DataSufficiencyLevel.L0_OHLCV_ONLY
    priority_score: float = Field(default=50, ge=0, le=100)
    approval_required: bool = True
    linked_thesis_id: str | None = None
    linked_strategy_id: str | None = None
    linked_task_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    public_seed_allowed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
