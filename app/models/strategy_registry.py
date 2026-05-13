from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StrategyLifecycleState(str, Enum):
    GENERATED = "generated"
    RISK_APPROVED = "risk_approved"
    BACKTEST_PASSED = "backtest_passed"
    PAPER_TRADING = "paper_trading"
    LIVE_CANDIDATE = "live_candidate"
    RETIRED = "retired"


class StrategyVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    code_hash: str = Field(min_length=1)
    parent_version_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    family: str = Field(min_length=1)
    lifecycle_state: StrategyLifecycleState
    current_version_id: str = Field(min_length=1)
    promoted_at: Optional[datetime] = None
    retired_at: Optional[datetime] = None
    retirement_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyLifecycleDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    from_state: StrategyLifecycleState
    to_state: StrategyLifecycleState
    approved: bool
    reasons: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StrategySimilarityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    compared_strategy_id: str = Field(min_length=1)
    similarity_score: float = Field(ge=0, le=1)
    is_duplicate: bool
    reasons: list[str]
