from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PaperOrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class PaperOrderStatus(str, Enum):
    FILLED = "filled"
    REJECTED = "rejected"


class PaperPositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class PaperEvaluationStatus(str, Enum):
    LIVE_CANDIDATE = "live_candidate"
    RETIRED = "retired"


class PaperTradingPlanStatus(str, Enum):
    PENDING_DATA = "pending_data"
    READY_FOR_PAPER = "ready_for_paper"
    COMPLETED = "completed"


class PaperTradingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    backtest_id: str = Field(min_length=1)
    status: PaperTradingPlanStatus
    required_symbol: str = Field(min_length=1)
    required_timeframe: str = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PaperPortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: str = Field(min_length=1)
    base_currency: str = "USDT"
    starting_cash: float = Field(gt=0)
    cash: float = Field(ge=0)
    equity: float = Field(ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PaperOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: PaperOrderSide
    quantity: float = Field(gt=0)
    requested_price: float = Field(gt=0)
    status: PaperOrderStatus
    reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def rejected_orders_need_reason(self) -> "PaperOrder":
        if self.status == PaperOrderStatus.REJECTED and not self.reason:
            raise ValueError("rejected paper orders must include reason")
        return self


class PaperFill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fill_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: PaperOrderSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(ge=0)
    slippage: float = Field(ge=0)
    filled_at: datetime = Field(default_factory=datetime.utcnow)


class PaperPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    quantity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    exit_price: Optional[float] = Field(default=None, gt=0)
    realized_pnl: float = 0
    status: PaperPositionStatus
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None

    @model_validator(mode="after")
    def closed_positions_need_exit(self) -> "PaperPosition":
        if self.status == PaperPositionStatus.CLOSED and self.exit_price is None:
            raise ValueError("closed paper positions must include exit_price")
        return self


class PaperTradingReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    trades: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=1)
    total_return: float
    max_drawdown: float = Field(le=0)
    profit_factor: float = Field(ge=0)
    status: PaperEvaluationStatus
    notes: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PaperVsBacktestComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparison_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    backtest_total_return: float
    paper_total_return: float
    backtest_profit_factor: float
    paper_profit_factor: float
    return_delta: float
    profit_factor_delta: float
    is_consistent: bool
    notes: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
