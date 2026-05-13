from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExperimentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(min_length=1)
    thesis_id: Optional[str] = None
    signal_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    backtest_id: str = Field(min_length=1)
    backtest_mode: str = Field(min_length=1)
    timerange: str = Field(pattern=r"^\d{8}-\d{8}$")
    strategy_code_hash: str = Field(min_length=64, max_length=64)
    config_hash: Optional[str] = Field(default=None, min_length=64, max_length=64)
    data_fingerprint: str = Field(min_length=64, max_length=64)
    freqtrade_version: Optional[str] = None
    command: list[str] = Field(default_factory=list)
    result_path: Optional[str] = None
    fee_model: dict[str, Any] = Field(default_factory=dict)
    slippage_model: dict[str, Any] = Field(default_factory=dict)
    random_seed: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
