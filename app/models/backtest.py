from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BacktestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class BacktestReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backtest_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    timerange: str = Field(pattern=r"^\d{8}-\d{8}$")
    trades: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=1)
    profit_factor: float = Field(ge=0)
    sharpe: Optional[float] = None
    max_drawdown: float = Field(le=0)
    total_return: float
    status: BacktestStatus
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def failed_reports_explain_zero_trade_runs(self) -> "BacktestReport":
        if self.status == BacktestStatus.FAILED and self.trades == 0 and not self.error:
            raise ValueError("failed zero-trade backtests must include an error")
        return self


class MonteCarloBacktestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulations: int = Field(default=500, ge=10, le=100_000)
    horizon_trades: int = Field(default=100, ge=1, le=10_000)
    seed: Optional[int] = None
    expensive_simulation_threshold: int = Field(default=250_000, ge=1)


class MonteCarloBacktestReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    source_backtest_id: str = Field(min_length=1)
    simulations: int = Field(ge=1)
    horizon_trades: int = Field(ge=1)
    expected_return_mean: float
    median_return: float
    p05_return: float
    p95_return: float
    probability_of_loss: float = Field(ge=0, le=1)
    probability_of_20pct_drawdown: float = Field(ge=0, le=1)
    max_drawdown_median: float = Field(le=0)
    max_drawdown_p05: float = Field(le=0)
    requires_human_confirmation: bool
    approved_to_run: bool
    notes: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
