from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataQualityFlag(str, Enum):
    MISSING_DATA = "missing_data"
    STALE_DATA = "stale_data"
    NON_POSITIVE_PRICE = "non_positive_price"
    NON_POSITIVE_VOLUME = "non_positive_volume"
    INVALID_ORDERBOOK = "invalid_orderbook"
    OUTLIER = "outlier"


class OhlcvCandle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    quote_volume: float = Field(ge=0)
    trade_count: int = Field(ge=0)
    raw: list[Any]

    @model_validator(mode="after")
    def high_low_bounds_prices(self) -> "OhlcvCandle":
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be greater than or equal to open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be less than or equal to open, close, and high")
        return self


class FundingRatePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    funding_time: datetime
    funding_rate: float
    mark_price: Optional[float] = None
    raw: dict[str, Any]


class OpenInterestPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    timestamp: datetime
    open_interest: float = Field(ge=0)
    raw: dict[str, Any]


class AggregateTrade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    aggregate_trade_id: int = Field(ge=0)
    price: float = Field(gt=0)
    quantity: float = Field(ge=0)
    first_trade_id: int = Field(ge=0)
    last_trade_id: int = Field(ge=0)
    timestamp: datetime
    buyer_is_maker: bool
    raw: dict[str, Any]


class OrderBookLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float = Field(gt=0)
    quantity: float = Field(ge=0)


class OrderBookSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    captured_at: datetime
    last_update_id: int
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    raw: dict[str, Any]

    @model_validator(mode="after")
    def must_have_both_sides(self) -> "OrderBookSnapshot":
        if not self.bids or not self.asks:
            raise ValueError("order book must include bids and asks")
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("best bid must be below best ask")
        return self


class DataQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    is_usable: bool
    flags: list[DataQualityFlag]
    details: list[str]


class AlternativeDataProvider(str, Enum):
    GLASSNODE = "glassnode"
    NANSEN = "nansen"


class AlternativeDataMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: AlternativeDataProvider
    metric_id: str = Field(min_length=1)
    symbol: Optional[str] = None
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    value: float | int | str | bool
    tags: dict[str, str] = Field(default_factory=dict)
    raw: dict[str, Any]
