from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.cost import BacktestCostModel
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


class HarnessBudgetDecisionAction(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


class StrategyScreeningAction(str, Enum):
    DEEPEN_VALIDATION = "deepen_validation"
    UPGRADE_DATA = "upgrade_data"
    ROTATE_STRATEGY_FAMILY = "rotate_strategy_family"
    RECORD_FAILURE = "record_failure"
    NEEDS_MORE_COVERAGE = "needs_more_coverage"
    WATCHLIST_REVIEW = "watchlist_review"


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


class HarnessBudgetPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_automatic_task_cost: int = Field(default=50, ge=1)
    max_optimizer_trials_per_strategy: int = Field(default=100, ge=1)
    max_repeated_failure_loops: int = Field(default=3, ge=1)
    max_autonomy_level_without_approval: int = Field(default=2, ge=0, le=5)


class HarnessBudgetDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    action: HarnessBudgetDecisionAction
    reasons: list[str] = Field(default_factory=list)
    original_status: ResearchTaskStatus
    resulting_status: ResearchTaskStatus
    approval_required: bool
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


class RegimeBucketStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regime: str = Field(min_length=1)
    candle_count: int = Field(ge=0)
    share: float = Field(ge=0, le=1)
    average_return: float = 0
    realized_volatility: float = Field(default=0, ge=0)
    trend_return: float = 0


class RegimeCoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_family: str = Field(min_length=1)
    symbols: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    buckets: list[RegimeBucketStats] = Field(default_factory=list)
    is_coverage_balanced: bool = False
    dominant_regime: str | None = None
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyFamilyBaselineRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_family: str = Field(min_length=1)
    display_name: str = Field(default="", min_length=0)
    description: str = Field(min_length=1)
    direction_bias: str = Field(default="unknown", min_length=1)
    benchmark_group: str = Field(default="generic", min_length=1)
    return_basis: str = Field(default="unknown", min_length=1)
    total_return: float
    gross_return: float = 0
    net_return: float = 0
    cost_drag: float = 0
    fee_drag: float = 0
    slippage_drag: float = 0
    funding_drag: float = 0
    profit_factor: float = Field(ge=0)
    gross_profit_factor: float = Field(default=0, ge=0)
    net_profit_factor: float = Field(default=0, ge=0)
    sharpe: float | None = None
    max_drawdown: float = Field(le=0)
    gross_max_drawdown: float = Field(default=0, le=0)
    net_max_drawdown: float = Field(default=0, le=0)
    trades: int = Field(ge=0)
    portfolio_period_count: int = Field(default=0, ge=0)
    positive_cell_count: int = Field(default=0, ge=0)
    tested_cell_count: int = Field(default=0, ge=0)


class StrategyFamilyBaselineBoard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_id: str = Field(min_length=1)
    symbols: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    timeframe_scope: str = Field(default="all_common_window", min_length=1)
    common_start_at: datetime | None = None
    common_end_at: datetime | None = None
    is_common_window_aligned: bool = False
    cost_model: BacktestCostModel = Field(default_factory=BacktestCostModel)
    rows: list[StrategyFamilyBaselineRow] = Field(default_factory=list)
    best_family: str | None = None
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BaselineImpliedRegimeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    source_baseline_board_id: str = Field(min_length=1)
    regime_label: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    component_scores: dict[str, float] = Field(default_factory=dict)
    leading_baselines: list[str] = Field(default_factory=list)
    lagging_baselines: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DataSufficiencyGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str = Field(min_length=1)
    strategy_family: str = Field(min_length=1)
    available_level: DataSufficiencyLevel
    minimum_validation_level: DataSufficiencyLevel
    recommended_next_level: DataSufficiencyLevel
    can_continue: bool
    should_upgrade_data: bool
    missing_evidence: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyScreeningDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1)
    strategy_family: str = Field(min_length=1)
    action: StrategyScreeningAction
    confidence: float = Field(ge=0, le=1)
    rationale: list[str] = Field(default_factory=list)
    next_tasks: list[ResearchTask] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyFamilyWalkForwardWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    trial_id: str = Field(min_length=1)
    fold_index: int = Field(ge=0)
    start_at: datetime
    end_at: datetime
    trade_count: int = Field(ge=0)
    total_return: float
    profit_factor: float = Field(ge=0)
    sharpe: float | None = None
    max_drawdown: float = Field(le=0)
    baseline_total_return: float
    baseline_trade_count: int = Field(ge=0)
    beats_baseline: bool
    passed: bool
    findings: list[str] = Field(default_factory=list)


class StrategyFamilyWalkForwardReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_family: str = Field(min_length=1)
    source_universe_report_id: str = Field(min_length=1)
    folds: int = Field(ge=1)
    min_trades_per_window: int = Field(ge=1)
    completed_windows: int = Field(ge=0)
    passed_windows: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    passed: bool
    windows: list[StrategyFamilyWalkForwardWindow] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyFamilyMonteCarloReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_family: str = Field(min_length=1)
    source_universe_report_id: str = Field(min_length=1)
    source_trial_ids: list[str] = Field(default_factory=list)
    simulations: int = Field(ge=1)
    horizon_trades: int = Field(ge=1)
    sampled_trade_count: int = Field(ge=0)
    expected_return_mean: float
    median_return: float
    p05_return: float
    p95_return: float
    probability_of_loss: float = Field(ge=0, le=1)
    max_drawdown_median: float = Field(le=0)
    max_drawdown_p05: float = Field(le=0)
    requires_human_confirmation: bool
    approved_to_run: bool
    passed: bool
    findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyFamilyOrderflowAcceptanceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    trial_id: str = Field(min_length=1)
    side: str = Field(min_length=1)
    event_time: datetime
    trade_return: float
    total_aggressive_volume: float = Field(ge=0)
    taker_buy_ratio: float = Field(ge=0, le=1)
    net_taker_volume: float
    cvd_change: float
    confirms_failure: bool
    conflicts_with_failure: bool
    notes: list[str] = Field(default_factory=list)


class StrategyFamilyOrderflowAcceptanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    strategy_family: str = Field(min_length=1)
    source_universe_report_id: str = Field(min_length=1)
    events_analyzed: int = Field(ge=0)
    events_with_orderflow: int = Field(ge=0)
    confirms_failure_count: int = Field(ge=0)
    conflicts_count: int = Field(ge=0)
    confirmation_rate: float = Field(ge=0, le=1)
    conflict_rate: float = Field(ge=0, le=1)
    passed: bool
    events: list[StrategyFamilyOrderflowAcceptanceEvent] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
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
    level_source: str = Field(default="rolling_extreme", min_length=1)
    level_lookback_bars: int = Field(ge=1)
    level_quality_threshold: float = Field(default=0, ge=0, le=100)
    breakout_depth_bps: float = Field(ge=0)
    acceptance_window_bars: int = Field(ge=1)
    acceptance_failure_threshold: float = Field(default=0, ge=0, le=100)
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
    event_funnel: dict[str, int] = Field(default_factory=dict)
    level_source_counts: dict[str, int] = Field(default_factory=dict)
    average_level_quality_score: float = 0
    average_acceptance_failure_score: float = 0


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
    event_funnel: dict[str, int] = Field(default_factory=dict)
    level_source_counts: dict[str, int] = Field(default_factory=dict)
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
