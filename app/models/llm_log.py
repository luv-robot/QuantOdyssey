from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PromptLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    model: str = Field(min_length=1)
    signal_id: Optional[str] = None
    strategy_id: Optional[str] = None
    prompt_version: str = Field(min_length=1)
    prompt_text: str = Field(min_length=1)
    input_payload: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ModelResponseLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_id: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    model: str = Field(min_length=1)
    output_payload: dict
    parsed_ok: bool
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
