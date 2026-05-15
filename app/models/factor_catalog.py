from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.research import DataSufficiencyLevel, EvaluationType, StrategyFamily


class FactorCatalogSource(str, Enum):
    WORLDQUANT_101_STYLE = "worldquant_101_style"


class FactorEvaluationScope(str, Enum):
    SINGLE_ASSET_TIME_SERIES = "single_asset_time_series"
    CROSS_SECTIONAL_UNIVERSE = "cross_sectional_universe"
    PORTFOLIO_CONTEXT = "portfolio_context"


class FactorImplementationStatus(str, Enum):
    PORTABLE_OHLCV = "portable_ohlcv"
    NEEDS_CROSS_SECTIONAL_UNIVERSE = "needs_cross_sectional_universe"
    NEEDS_EXTRA_DATA = "needs_extra_data"
    TEMPLATE_ONLY = "template_only"


class FactorFormulaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_id: str = Field(min_length=1)
    source: FactorCatalogSource
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    formula_expression: str = Field(min_length=1)
    factor_family: str = Field(min_length=1)
    strategy_family: StrategyFamily = StrategyFamily.GENERAL_OR_UNKNOWN
    evaluation_type: EvaluationType = EvaluationType.CONTINUOUS_ALPHA
    evaluation_scope: FactorEvaluationScope
    implementation_status: FactorImplementationStatus
    data_sufficiency_level: DataSufficiencyLevel = DataSufficiencyLevel.L0_OHLCV_ONLY
    required_fields: list[str] = Field(default_factory=list)
    required_operators: list[str] = Field(default_factory=list)
    lookback_windows: list[int] = Field(default_factory=list)
    baseline_roles: list[str] = Field(default_factory=list)
    crypto_compatibility_notes: list[str] = Field(default_factory=list)
    overfitting_warnings: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    license_note: str = Field(default="WorldQuant-style metadata only; no third-party code is copied.", min_length=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FactorFormulaCatalogReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    source: FactorCatalogSource
    total_items: int = Field(ge=0)
    family_counts: dict[str, int] = Field(default_factory=dict)
    scope_counts: dict[str, int] = Field(default_factory=dict)
    implementation_status_counts: dict[str, int] = Field(default_factory=dict)
    data_level_counts: dict[str, int] = Field(default_factory=dict)
    baseline_candidate_count: int = Field(ge=0)
    factor_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
