from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResearchAssetIndexEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    asset_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    thesis_id: str | None = None
    signal_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    linked_artifacts: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
