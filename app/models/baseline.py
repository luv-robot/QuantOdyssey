from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BaselineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    total_return: float
    profit_factor: float = Field(ge=0)
    sharpe: Optional[float] = None
    max_drawdown: float = Field(le=0)
    trades: int = Field(ge=0)


class BaselineComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    source_backtest_id: str = Field(min_length=1)
    strategy_total_return: float
    strategy_profit_factor: float = Field(ge=0)
    best_baseline_name: str = Field(min_length=1)
    best_baseline_return: float
    outperformed_best_baseline: bool
    baselines: list[BaselineResult] = Field(min_length=1)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
