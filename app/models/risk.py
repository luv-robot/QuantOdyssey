from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1)
    severity: RiskSeverity
    message: str = Field(min_length=1)


class RiskAuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    approved: bool
    findings: list[RiskFinding]
    audited_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def rejected_results_need_findings(self) -> "RiskAuditResult":
        if not self.approved and not self.findings:
            raise ValueError("rejected risk audit must include findings")
        return self
