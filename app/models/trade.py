from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MarketRegime(str, Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_LIQUIDITY = "low_liquidity"
    FUNDING_EXTREME = "funding_extreme"
    MARKET_SYNC_DOWN = "market_sync_down"


class TradeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trade_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    opened_at: datetime
    closed_at: datetime
    entry_price: float = Field(gt=0)
    exit_price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    profit_abs: float
    profit_pct: float
    fees: float = Field(ge=0)


class TradeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    trades: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=1)
    total_profit_abs: float
    total_profit_pct: float
    average_profit_pct: float
    largest_loss_pct: float
    largest_win_pct: float


class RegimeReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    regime: MarketRegime
    trades: int = Field(ge=0)
    total_profit_pct: float
    win_rate: float = Field(ge=0, le=1)
    notes: list[str]


class FailureDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1)
    severity: str = Field(pattern="^(low|medium|high)$")
    evidence: list[str] = Field(min_length=1)
    recommendation: str = Field(min_length=1)


class EnhancedReviewMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    signal_rank_score: int = Field(ge=0, le=100)
    realized_return: float
    rank_return_alignment: float
    trade_summary: TradeSummary
    regime_reviews: list[RegimeReview]
    failure_patterns: list[str]
    reusable_lessons: list[str]
    failure_diagnoses: list[FailureDiagnosis] = Field(default_factory=list)
    evaluation_score: float = Field(default=0, ge=0, le=100)
    evaluation_components: dict[str, float] = Field(default_factory=dict)
