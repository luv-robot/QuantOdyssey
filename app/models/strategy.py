from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrategyStatus(str, Enum):
    GENERATED = "generated"
    RISK_APPROVED = "risk_approved"
    RISK_REJECTED = "risk_rejected"
    BACKTESTED = "backtested"
    RETIRED = "retired"


class StrategyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    thesis_id: Optional[str] = None
    name: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    generated_at: datetime
    timeframe: str = Field(min_length=1)
    symbols: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    failure_modes: list[str] = Field(min_length=1)
    status: StrategyStatus = StrategyStatus.GENERATED

    @field_validator("name")
    @classmethod
    def name_must_be_python_identifier(cls, value: str) -> str:
        if not value.isidentifier():
            raise ValueError("strategy name must be a valid Python identifier")
        return value
