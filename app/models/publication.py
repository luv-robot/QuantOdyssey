from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.research import EvaluationType, StrategyFamily


class PublicArtifactStatus(str, Enum):
    DRAFT = "draft"
    REVIEW_READY = "review_ready"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PublicArtifactVisibility(str, Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"
    ARENA_SUBMITTED = "arena_submitted"


class PublicThesisCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: str = Field(min_length=1)
    thesis_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    strategy_family: StrategyFamily = StrategyFamily.GENERAL_OR_UNKNOWN
    evaluation_type: EvaluationType | None = None
    visibility: PublicArtifactVisibility = PublicArtifactVisibility.PRIVATE
    status: PublicArtifactStatus = PublicArtifactStatus.DRAFT
    public_summary: str = Field(min_length=1)
    market_observation_summary: str = Field(min_length=1)
    hypothesis_summary: str = Field(min_length=1)
    data_requirements: list[str] = Field(default_factory=list)
    baseline_summary: str | None = None
    regime_notes: list[str] = Field(default_factory=list)
    ai_review_summary: str | None = None
    next_experiments: list[str] = Field(default_factory=list)
    public_metrics: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    linked_public_strategy_ids: list[str] = Field(default_factory=list)
    redacted_fields: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PublicStrategyCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    thesis_id: str | None = None
    title: str = Field(min_length=1)
    strategy_family: StrategyFamily = StrategyFamily.GENERAL_OR_UNKNOWN
    visibility: PublicArtifactVisibility = PublicArtifactVisibility.PRIVATE
    status: PublicArtifactStatus = PublicArtifactStatus.DRAFT
    public_description: str = Field(min_length=1)
    evaluation_summary: str = Field(min_length=1)
    public_metrics: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    benchmark_refs: list[str] = Field(default_factory=list)
    redacted_fields: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
