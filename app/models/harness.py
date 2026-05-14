from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.research import DataSufficiencyLevel


class ResearchTaskStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    REJECTED = "rejected"


class ResearchTaskType(str, Enum):
    EVENT_FREQUENCY_SCAN = "event_frequency_scan"
    BASELINE_TEST = "baseline_test"
    EVENT_DEFINITION_TEST = "event_definition_test"
    REGIME_BUCKET_TEST = "regime_bucket_test"
    CROSS_SYMBOL_TEST = "cross_symbol_test"
    WALK_FORWARD_TEST = "walk_forward_test"
    OUT_OF_SAMPLE_TEST = "out_of_sample_test"
    MONTE_CARLO_TEST = "monte_carlo_test"
    PARAMETER_SENSITIVITY_TEST = "parameter_sensitivity_test"
    DATA_SUFFICIENCY_REVIEW = "data_sufficiency_review"
    EXTERNAL_DATA_NEED_REVIEW = "external_data_need_review"
    FAILURE_CLUSTER_REVIEW = "failure_cluster_review"
    WATCHLIST_REVIEW = "watchlist_review"
    STRATEGY_FAMILY_PRIORITY_REVIEW = "strategy_family_priority_review"


class ResearchFindingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResearchTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    task_type: ResearchTaskType
    subject_type: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    thesis_id: str | None = None
    signal_id: str | None = None
    strategy_id: str | None = None
    hypothesis: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    required_experiments: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    failure_conditions: list[str] = Field(default_factory=list)
    required_data_level: DataSufficiencyLevel = DataSufficiencyLevel.L0_OHLCV_ONLY
    estimated_cost: int = Field(default=1, ge=1)
    priority_score: float = Field(ge=0, le=100)
    status: ResearchTaskStatus = ResearchTaskStatus.PROPOSED
    approval_required: bool = False
    autonomy_level: int = Field(default=1, ge=0, le=5)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(min_length=1)
    thesis_id: str | None = None
    signal_id: str = Field(min_length=1)
    strategy_id: str | None = None
    finding_type: str = Field(min_length=1)
    severity: ResearchFindingSeverity
    summary: str = Field(min_length=1)
    observations: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    next_task_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchHarnessCycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str = Field(min_length=1)
    thesis_id: str | None = None
    signal_id: str = Field(min_length=1)
    source: str = Field(default="human_research_pipeline", min_length=1)
    finding_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EventDefinitionSensitivityTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trial_id: str = Field(min_length=1)
    funding_percentile_threshold: float = Field(ge=0, le=100)
    oi_percentile_threshold: float = Field(ge=0, le=100)
    failed_breakout_window: int = Field(ge=1)
    oi_retreat_threshold: float = Field(ge=0)
    event_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    average_return: float
    total_return: float
    profit_factor: float
    sharpe: float | None = None
    max_drawdown: float
    beats_cash: bool
    beats_funding_only: bool


class EventDefinitionSensitivityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    task_id: str | None = None
    thesis_id: str | None = None
    signal_id: str | None = None
    strategy_id: str | None = None
    strategy_family: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    horizon_hours: int = Field(ge=1)
    search_budget_trials: int = Field(ge=0)
    completed_trials: int = Field(ge=0)
    funding_only_total_return: float
    funding_only_profit_factor: float
    funding_only_trade_count: int = Field(ge=0)
    best_trial: EventDefinitionSensitivityTrial | None = None
    robust_trial_count: int = Field(ge=0)
    min_trade_count: int = Field(ge=1)
    trials: list[EventDefinitionSensitivityTrial] = Field(default_factory=list)
    data_warnings: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EventDefinitionUniverseCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    completed_trials: int = Field(ge=0)
    robust_trial_count: int = Field(ge=0)
    funding_only_total_return: float
    funding_only_trade_count: int = Field(ge=0)
    best_trial_id: str | None = None
    best_trial_trade_count: int = Field(default=0, ge=0)
    best_trial_total_return: float = 0
    best_trial_profit_factor: float = 0
    best_trial_sharpe: float | None = None
    data_warnings: list[str] = Field(default_factory=list)


class EventDefinitionUniverseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    task_id: str | None = None
    thesis_id: str | None = None
    signal_id: str | None = None
    strategy_family: str = Field(min_length=1)
    symbols: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    completed_cells: int = Field(ge=0)
    skipped_cells: list[str] = Field(default_factory=list)
    min_market_confirmations: int = Field(ge=1)
    robust_trial_ids: list[str] = Field(default_factory=list)
    best_trial_frequency: dict[str, int] = Field(default_factory=dict)
    cells: list[EventDefinitionUniverseCell] = Field(default_factory=list)
    child_report_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FailedBreakoutSensitivityTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trial_id: str = Field(min_length=1)
    side: str = Field(min_length=1)
    level_lookback_bars: int = Field(ge=1)
    breakout_depth_bps: float = Field(ge=0)
    acceptance_window_bars: int = Field(ge=1)
    volume_zscore_threshold: float = Field(ge=0)
    event_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    average_return: float
    total_return: float
    profit_factor: float
    sharpe: float | None = None
    max_drawdown: float
    beats_cash: bool
    beats_simple_failed_breakout: bool


class FailedBreakoutSensitivityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    task_id: str | None = None
    thesis_id: str | None = None
    signal_id: str | None = None
    strategy_id: str | None = None
    strategy_family: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    horizon_hours: int = Field(ge=1)
    search_budget_trials: int = Field(ge=0)
    completed_trials: int = Field(ge=0)
    simple_failed_breakout_total_return: float
    simple_failed_breakout_profit_factor: float
    simple_failed_breakout_trade_count: int = Field(ge=0)
    best_trial: FailedBreakoutSensitivityTrial | None = None
    robust_trial_count: int = Field(ge=0)
    min_trade_count: int = Field(ge=1)
    trials: list[FailedBreakoutSensitivityTrial] = Field(default_factory=list)
    data_warnings: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FailedBreakoutUniverseCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    completed_trials: int = Field(ge=0)
    robust_trial_count: int = Field(ge=0)
    simple_failed_breakout_total_return: float
    simple_failed_breakout_trade_count: int = Field(ge=0)
    best_trial_id: str | None = None
    best_trial_trade_count: int = Field(default=0, ge=0)
    best_trial_total_return: float = 0
    best_trial_profit_factor: float = 0
    best_trial_sharpe: float | None = None
    data_warnings: list[str] = Field(default_factory=list)


class FailedBreakoutUniverseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    task_id: str | None = None
    thesis_id: str | None = None
    signal_id: str | None = None
    strategy_family: str = Field(min_length=1)
    symbols: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    completed_cells: int = Field(ge=0)
    skipped_cells: list[str] = Field(default_factory=list)
    min_market_confirmations: int = Field(ge=1)
    robust_trial_ids: list[str] = Field(default_factory=list)
    best_trial_frequency: dict[str, int] = Field(default_factory=dict)
    cells: list[FailedBreakoutUniverseCell] = Field(default_factory=list)
    child_report_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
