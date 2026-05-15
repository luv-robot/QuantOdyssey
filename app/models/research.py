from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.strategy import StrategyManifest


class ThesisStatus(str, Enum):
    DRAFT = "draft"
    READY_FOR_IMPLEMENTATION = "ready_for_implementation"
    TESTING = "testing"
    SUPPORTED = "supported"
    REJECTED = "rejected"


class PreReviewStatus(str, Enum):
    READY_FOR_DESIGN = "ready_for_design"
    NEEDS_CLARIFICATION = "needs_clarification"
    CAN_PROCEED_WITH_ASSUMPTIONS = "can_proceed_with_assumptions"


class PreReviewQuestionCategory(str, Enum):
    COMPLETENESS = "completeness"
    CLARITY = "clarity"
    COMMONNESS = "commonness"
    DATA = "data"
    RISK = "risk"


class StrategyFamily(str, Enum):
    LIQUIDITY_SWEEP_REVERSAL = "liquidity_sweep_reversal"
    LIQUIDATION_CASCADE_REVERSAL = "liquidation_cascade_reversal"
    FUNDING_CROWDING_FADE = "funding_crowding_fade"
    FAILED_BREAKOUT_PUNISHMENT = "failed_breakout_punishment"
    EVENT_OVERREACTION_FADE = "event_overreaction_fade"
    BASIS_FUNDING_DISLOCATION_REVERSION = "basis_funding_dislocation_reversion"
    TREND_TRAP_CONTINUATION = "trend_trap_continuation"
    VWAP_EXHAUSTION_REVERSION = "vwap_exhaustion_reversion"
    CONTINUOUS_TREND_OR_MOMENTUM = "continuous_trend_or_momentum"
    GENERAL_OR_UNKNOWN = "general_or_unknown"


class EvaluationType(str, Enum):
    CONTINUOUS_ALPHA = "continuous_alpha"
    EVENT_DRIVEN_ALPHA = "event_driven_alpha"
    TAIL_OR_CRISIS_ALPHA = "tail_or_crisis_alpha"
    PERMISSION_OR_FILTER = "permission_or_filter"


class DataSufficiencyLevel(str, Enum):
    L0_OHLCV_ONLY = "L0_ohlcv_only"
    L1_FUNDING_OI = "L1_ohlcv_funding_open_interest"
    L2_ORDERFLOW_LIQUIDATION = "L2_orderflow_liquidation"
    L3_ONCHAIN_NARRATIVE = "L3_onchain_narrative"


class ThesisDataContractStatus(str, Enum):
    COMPATIBLE = "compatible"
    NEEDS_THESIS_SEED = "needs_thesis_seed"
    BLOCKED = "blocked"


class ResearchThesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thesis_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    author: str = Field(default="human", min_length=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: ThesisStatus = ThesisStatus.DRAFT
    market_observation: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    trade_logic: str = Field(min_length=1)
    expected_regimes: list[str] = Field(min_length=1)
    invalidation_conditions: list[str] = Field(min_length=1)
    risk_notes: list[str] = Field(default_factory=list)
    linked_signal_ids: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class ThesisDataContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_id: str = Field(min_length=1)
    thesis_id: str = Field(min_length=1)
    signal_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: ThesisDataContractStatus
    can_run: bool = False
    requested_timeframe: Optional[str] = None
    requested_data: list[str] = Field(default_factory=list)
    requested_side: Optional[str] = None
    signal_timeframe: Optional[str] = None
    signal_data_sources: list[str] = Field(default_factory=list)
    signal_type: Optional[str] = None
    mismatches: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_action: str = Field(min_length=1)


class PreReviewQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: PreReviewQuestionCategory
    question: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    blocks_design_quality: bool = True


class ThesisPreReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pre_review_id: str = Field(min_length=1)
    thesis_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: PreReviewStatus
    completeness_score: float = Field(ge=0, le=100)
    condition_clarity_score: float = Field(ge=0, le=100)
    commonness_risk_score: float = Field(ge=0, le=100)
    structure_findings: list[str] = Field(default_factory=list)
    clarity_findings: list[str] = Field(default_factory=list)
    commonness_findings: list[str] = Field(default_factory=list)
    questions: list[PreReviewQuestion] = Field(default_factory=list, max_length=8)
    assumptions_if_proceed: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    hypothesis_drift_risk: str = Field(default="low", min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)


class ResearchDesignDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    design_id: str = Field(min_length=1)
    thesis_id: str = Field(min_length=1)
    pre_review_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    thesis_summary: str = Field(min_length=1)
    inferred_strategy_family: StrategyFamily
    evaluation_type: EvaluationType
    data_sufficiency_level: DataSufficiencyLevel
    validation_data_sufficiency_level: DataSufficiencyLevel = DataSufficiencyLevel.L0_OHLCV_ONLY
    missing_evidence: list[str] = Field(default_factory=list)
    event_definition_draft: str = Field(min_length=1)
    baseline_set: list[str] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    what_this_tests: list[str] = Field(default_factory=list)
    what_this_does_not_test: list[str] = Field(default_factory=list)
    ai_assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    proceed_recommendation: PreReviewStatus


class EventEpisodeStage(str, Enum):
    SETUP = "setup"
    TRIGGER = "trigger"
    TRADE = "trade"


class EventEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    thesis_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    strategy_family: StrategyFamily
    evaluation_type: EvaluationType
    stage: EventEpisodeStage = EventEpisodeStage.SETUP
    direction: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    setup_window_bars: int = Field(default=288, ge=1)
    trigger_window_bars: int = Field(default=3, ge=1)
    data_sufficiency_level: DataSufficiencyLevel
    validation_data_sufficiency_level: DataSufficiencyLevel
    trigger_definition: str = Field(min_length=1)
    features: dict[str, float | int | str | bool] = Field(default_factory=dict)
    missing_evidence: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    thesis_id: Optional[str] = None
    manifest: StrategyManifest
    strategy_code: str = Field(min_length=1)
    score: float = Field(ge=0, le=100)
    ranking_reasons: list[str]
    template_name: str = Field(min_length=1)
    indicators: list[str]


class CandidateRankingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(min_length=1)
    thesis_id: Optional[str] = None
    candidates: list[StrategyCandidate]
    selected_candidate_id: Optional[str] = None
