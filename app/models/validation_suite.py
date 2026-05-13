from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SymbolValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    backtest_id: str = Field(min_length=1)
    total_return: float
    profit_factor: float = Field(ge=0)
    sharpe: float | None = None
    max_drawdown: float = Field(le=0)
    trades: int = Field(ge=0)
    passed: bool
    classification: str = Field(min_length=1)


class CrossSymbolValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    source_backtest_id: str = Field(min_length=1)
    primary_symbol: str = Field(min_length=1)
    related_symbols: list[str] = Field(default_factory=list)
    stress_symbols: list[str] = Field(default_factory=list)
    results: list[SymbolValidationResult] = Field(default_factory=list)
    pass_rate: float = Field(ge=0, le=1)
    robustness_label: str = Field(min_length=1)
    passed: bool
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RealBacktestValidationSuiteReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    source_backtest_id: str = Field(min_length=1)
    out_of_sample_backtest_id: str | None = None
    walk_forward_backtest_ids: list[str] = Field(default_factory=list)
    fee_slippage_backtest_id: str | None = None
    cross_symbol_report_id: str | None = None
    executed: bool
    passed: bool
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
