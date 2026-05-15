from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SignalType(str, Enum):
    VOLUME_SPIKE = "volume_spike"
    FUNDING_OI_EXTREME = "funding_oi_extreme"
    ORDERBOOK_IMBALANCE = "orderbook_imbalance"
    LIQUIDATION_CLUSTER = "liquidation_cluster"
    THESIS_SEED = "thesis_seed"


class MarketSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(min_length=1)
    created_at: datetime
    market: str = Field(default="crypto")
    exchange: str
    symbol: str
    timeframe: str = Field(min_length=1)
    signal_type: SignalType
    rank_score: int = Field(ge=0, le=100)
    features: dict[str, Union[float, int, str, bool]]
    hypothesis: str = Field(min_length=1)
    data_sources: list[str] = Field(min_length=1)

    @field_validator("exchange")
    @classmethod
    def exchange_must_be_supported(cls, value: str) -> str:
        if value.lower() not in {"binance", "okx", "bybit"}:
            raise ValueError("unsupported exchange")
        return value.lower()

    @field_validator("symbol")
    @classmethod
    def symbol_must_be_pair(cls, value: str) -> str:
        if "/" not in value:
            raise ValueError("symbol must use BASE/QUOTE format")
        return value.upper()
