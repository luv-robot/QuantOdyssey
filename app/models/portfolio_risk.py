from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PortfolioRiskSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCK = "block"


class PortfolioExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    notional: float = Field(ge=0)
    unrealized_pnl: float = 0
    correlation_group: str = Field(min_length=1)


class PortfolioRiskLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_total_exposure: float = Field(gt=0)
    max_symbol_concentration: float = Field(gt=0, le=1)
    max_daily_loss: float = Field(le=0)
    max_strategy_drawdown: float = Field(le=0)
    max_correlated_exposure: float = Field(gt=0)
    cooldown_minutes: int = Field(ge=0)
    kill_switch_enabled: bool = False


class PortfolioRiskFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1)
    severity: PortfolioRiskSeverity
    message: str = Field(min_length=1)


class PortfolioRiskReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    approved: bool
    findings: list[PortfolioRiskFinding]
    recommended_position_size: float = Field(ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
