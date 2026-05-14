from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.research import DataSufficiencyLevel


class ResearchTaskStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    REJECTED = "rejected"


class ResearchTaskType(str, Enum):
    EVENT_FREQUENCY_SCAN = "event_frequency_scan"
    BASELINE_TEST = "baseline_test"
    EVENT_DEFINITION_TEST = "event_definition_test"
    REGIME_BUCKET_TEST = "regime_bucket_test"
    CROSS_SYMBOL_TEST = "cross_symbol_test"
    WALK_FORWARD_TEST = "walk_forward_test"
    OUT_OF_SAMPLE_TEST = "out_of_sample_test"
    MONTE_CARLO_TEST = "monte_carlo_test"
    PARAMETER_SENSITIVITY_TEST = "parameter_sensitivity_test"
    DATA_SUFFICIENCY_REVIEW = "data_sufficiency_review"
    EXTERNAL_DATA_NEED_REVIEW = "external_data_need_review"
    FAILURE_CLUSTER_REVIEW = "failure_cluster_review"
    WATCHLIST_REVIEW = "watchlist_review"
    STRATEGY_FAMILY_PRIORITY_REVIEW = "strategy_family_priority_review"


class ResearchFindingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResearchTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    task_type: ResearchTaskType
    subject_type: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    thesis_id: str | None = None
    signal_id: str | None = None
    strategy_id: str | None = None
    hypothesis: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    required_experiments: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    failure_conditions: list[str] = Field(default_factory=list)
    required_data_level: DataSufficiencyLevel = DataSufficiencyLevel.L0_OHLCV_ONLY
    estimated_cost: int = Field(default=1, ge=1)
    priority_score: float = Field(ge=0, le=100)
    status: ResearchTaskStatus = ResearchTaskStatus.PROPOSED
    approval_required: bool = False
    autonomy_level: int = Field(default=1, ge=0, le=5)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(min_length=1)
    thesis_id: str | None = None
    signal_id: str = Field(min_length=1)
    strategy_id: str | None = None
    finding_type: str = Field(min_length=1)
    severity: ResearchFindingSeverity
    summary: str = Field(min_length=1)
    observations: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    next_task_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchHarnessCycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str = Field(min_length=1)
    thesis_id: str | None = None
    signal_id: str = Field(min_length=1)
    source: str = Field(default="human_research_pipeline", min_length=1)
    finding_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
