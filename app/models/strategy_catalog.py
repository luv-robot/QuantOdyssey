from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.research import EvaluationType, StrategyFamily


class StrategyCatalogSource(str, Enum):
    QUANTCONNECT_LEAN = "quantconnect_lean"


class StrategyCatalogLanguage(str, Enum):
    PYTHON = "python"
    CSHARP = "csharp"


class StrategyMigrationDifficulty(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StrategyCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1)
    source: StrategyCatalogSource
    source_repo_url: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    language: StrategyCatalogLanguage
    name: str = Field(min_length=1)
    class_names: list[str] = Field(default_factory=list)
    strategy_family: StrategyFamily = StrategyFamily.GENERAL_OR_UNKNOWN
    evaluation_type: EvaluationType = EvaluationType.CONTINUOUS_ALPHA
    asset_classes: list[str] = Field(default_factory=list)
    data_requirements: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    resolutions: list[str] = Field(default_factory=list)
    universe_features: list[str] = Field(default_factory=list)
    suggested_roles: list[str] = Field(default_factory=list)
    migration_difficulty: StrategyMigrationDifficulty = StrategyMigrationDifficulty.MEDIUM
    migration_notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    license: str = Field(default="Apache-2.0", min_length=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyCatalogReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    source: StrategyCatalogSource
    source_repo_url: str = Field(min_length=1)
    scanned_paths: list[str] = Field(default_factory=list)
    total_files_scanned: int = Field(ge=0)
    item_count: int = Field(ge=0)
    language_counts: dict[str, int] = Field(default_factory=dict)
    family_counts: dict[str, int] = Field(default_factory=dict)
    difficulty_counts: dict[str, int] = Field(default_factory=dict)
    suggested_role_counts: dict[str, int] = Field(default_factory=dict)
    item_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
