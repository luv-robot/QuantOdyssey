from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.models import (
    BacktestReport,
    BacktestValidationReport,
    BaselineComparisonReport,
    CrossSymbolValidationReport,
    DataQualityReport,
    EnhancedReviewMetrics,
    EventDefinitionSensitivityReport,
    EventDefinitionUniverseReport,
    EventEpisode,
    ExperimentManifest,
    FailedBreakoutSensitivityReport,
    FailedBreakoutUniverseReport,
    ExperimentQueueItem,
    FundingRatePoint,
    MarketSignal,
    MarketRegimeSnapshot,
    ModelResponseLog,
    NegativeResultCase,
    MonteCarloBacktestReport,
    OhlcvCandle,
    OpenInterestPoint,
    OrderBookSnapshot,
    PaperFill,
    PaperOrder,
    PaperPortfolio,
    PaperPosition,
    PaperTradingPlan,
    PaperTradingReport,
    PaperVsBacktestComparison,
    PortfolioRiskReport,
    PromptLog,
    ResearchDesignDraft,
    ResearchFinding,
    ResearchHarnessCycle,
    ResearchAssetIndexEntry,
    ResearchTask,
    ResearchThesis,
    ResourceBudgetReport,
    ReviewCase,
    ReviewSession,
    RealBacktestValidationSuiteReport,
    RobustnessReport,
    RiskAuditResult,
    StrategyFamilyMonteCarloReport,
    StrategyFamilyWalkForwardReport,
    StrategyManifest,
    StrategyLifecycleDecision,
    StrategyRegistryEntry,
    StrategySimilarityResult,
    StrategyVersion,
    TradeRecord,
    TradeSummary,
    ThesisPreReview,
    WorkflowRun,
)

Base = declarative_base()
ModelT = TypeVar("ModelT", bound=BaseModel)


class SignalRecord(Base):
    __tablename__ = "signals"

    signal_id = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResearchThesisRecord(Base):
    __tablename__ = "research_theses"

    thesis_id = Column(String, primary_key=True)
    status = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ThesisPreReviewRecord(Base):
    __tablename__ = "thesis_pre_reviews"

    pre_review_id = Column(String, primary_key=True)
    thesis_id = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResearchDesignDraftRecord(Base):
    __tablename__ = "research_design_drafts"

    design_id = Column(String, primary_key=True)
    thesis_id = Column(String, index=True, nullable=False)
    pre_review_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EventEpisodeRecord(Base):
    __tablename__ = "event_episodes"

    event_id = Column(String, primary_key=True)
    thesis_id = Column(String, index=True, nullable=False)
    signal_id = Column(String, index=True, nullable=False)
    strategy_family = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResearchAssetIndexRecord(Base):
    __tablename__ = "research_asset_index"

    asset_id = Column(String, primary_key=True)
    asset_type = Column(String, index=True, nullable=False)
    signal_id = Column(String, index=True, nullable=False)
    strategy_id = Column(String, index=True, nullable=False)
    thesis_id = Column(String, index=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MarketDataRecord(Base):
    __tablename__ = "market_data"

    dataset_id = Column(String, primary_key=True)
    data_type = Column(String, index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DataQualityRecord(Base):
    __tablename__ = "data_quality_reports"

    dataset_id = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MarketRegimeSnapshotRecord(Base):
    __tablename__ = "market_regime_snapshots"

    regime_id = Column(String, primary_key=True)
    signal_id = Column(String, index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    primary_regime = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyRecord(Base):
    __tablename__ = "strategies"

    strategy_id = Column(String, primary_key=True)
    signal_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RiskAuditRecord(Base):
    __tablename__ = "risk_audits"

    strategy_id = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class BacktestRecord(Base):
    __tablename__ = "backtests"

    backtest_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class BacktestValidationRecord(Base):
    __tablename__ = "backtest_validations"

    validation_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ExperimentManifestRecord(Base):
    __tablename__ = "experiment_manifests"

    experiment_id = Column(String, primary_key=True)
    thesis_id = Column(String, index=True)
    signal_id = Column(String, index=True, nullable=False)
    strategy_id = Column(String, index=True, nullable=False)
    backtest_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ExperimentQueueRecord(Base):
    __tablename__ = "experiment_queue"

    queue_id = Column(String, primary_key=True)
    status = Column(String, index=True, nullable=False)
    signal_id = Column(String, index=True, nullable=False)
    strategy_id = Column(String, index=True, nullable=False)
    candidate_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class BaselineComparisonRecord(Base):
    __tablename__ = "baseline_comparisons"

    report_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    signal_id = Column(String, index=True, nullable=False)
    source_backtest_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RobustnessReportRecord(Base):
    __tablename__ = "robustness_reports"

    report_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    source_backtest_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CrossSymbolValidationRecord(Base):
    __tablename__ = "cross_symbol_validations"

    report_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    source_backtest_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RealBacktestValidationSuiteRecord(Base):
    __tablename__ = "real_backtest_validation_suites"

    report_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    source_backtest_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MonteCarloBacktestRecord(Base):
    __tablename__ = "monte_carlo_backtests"

    report_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    source_backtest_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReviewRecord(Base):
    __tablename__ = "reviews"

    case_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    signal_id = Column(String, index=True, nullable=False)
    result = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReviewSessionRecord(Base):
    __tablename__ = "review_sessions"

    session_id = Column(String, primary_key=True)
    thesis_id = Column(String, index=True, nullable=False)
    signal_id = Column(String, index=True, nullable=False)
    strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NegativeResultRecord(Base):
    __tablename__ = "negative_result_cases"

    case_id = Column(String, primary_key=True)
    signal_id = Column(String, index=True, nullable=False)
    strategy_id = Column(String, index=True, nullable=False)
    candidate_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResearchFindingRecord(Base):
    __tablename__ = "research_findings"

    finding_id = Column(String, primary_key=True)
    signal_id = Column(String, index=True, nullable=False)
    strategy_id = Column(String, index=True)
    thesis_id = Column(String, index=True)
    finding_type = Column(String, index=True, nullable=False)
    severity = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResearchTaskRecord(Base):
    __tablename__ = "research_tasks"

    task_id = Column(String, primary_key=True)
    task_type = Column(String, index=True, nullable=False)
    subject_type = Column(String, index=True, nullable=False)
    subject_id = Column(String, index=True, nullable=False)
    signal_id = Column(String, index=True)
    strategy_id = Column(String, index=True)
    thesis_id = Column(String, index=True)
    status = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResearchHarnessCycleRecord(Base):
    __tablename__ = "research_harness_cycles"

    cycle_id = Column(String, primary_key=True)
    signal_id = Column(String, index=True, nullable=False)
    thesis_id = Column(String, index=True)
    source = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EventDefinitionSensitivityReportRecord(Base):
    __tablename__ = "event_definition_sensitivity_reports"

    report_id = Column(String, primary_key=True)
    task_id = Column(String, index=True)
    signal_id = Column(String, index=True)
    strategy_id = Column(String, index=True)
    thesis_id = Column(String, index=True)
    strategy_family = Column(String, index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EventDefinitionUniverseReportRecord(Base):
    __tablename__ = "event_definition_universe_reports"

    report_id = Column(String, primary_key=True)
    task_id = Column(String, index=True)
    signal_id = Column(String, index=True)
    thesis_id = Column(String, index=True)
    strategy_family = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FailedBreakoutSensitivityReportRecord(Base):
    __tablename__ = "failed_breakout_sensitivity_reports"

    report_id = Column(String, primary_key=True)
    task_id = Column(String, index=True)
    signal_id = Column(String, index=True)
    strategy_id = Column(String, index=True)
    thesis_id = Column(String, index=True)
    strategy_family = Column(String, index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FailedBreakoutUniverseReportRecord(Base):
    __tablename__ = "failed_breakout_universe_reports"

    report_id = Column(String, primary_key=True)
    task_id = Column(String, index=True)
    signal_id = Column(String, index=True)
    thesis_id = Column(String, index=True)
    strategy_family = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyFamilyWalkForwardReportRecord(Base):
    __tablename__ = "strategy_family_walk_forward_reports"

    report_id = Column(String, primary_key=True)
    strategy_family = Column(String, index=True, nullable=False)
    source_universe_report_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyFamilyMonteCarloReportRecord(Base):
    __tablename__ = "strategy_family_monte_carlo_reports"

    report_id = Column(String, primary_key=True)
    strategy_family = Column(String, index=True, nullable=False)
    source_universe_report_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WorkflowRunRecord(Base):
    __tablename__ = "workflow_runs"

    workflow_run_id = Column(String, primary_key=True)
    signal_id = Column(String, index=True, nullable=False)
    strategy_id = Column(String, index=True)
    state = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaperPortfolioRecord(Base):
    __tablename__ = "paper_portfolios"

    portfolio_id = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaperOrderRecord(Base):
    __tablename__ = "paper_orders"

    order_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaperFillRecord(Base):
    __tablename__ = "paper_fills"

    fill_id = Column(String, primary_key=True)
    order_id = Column(String, index=True, nullable=False)
    strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaperPositionRecord(Base):
    __tablename__ = "paper_positions"

    position_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaperTradingReportRecord(Base):
    __tablename__ = "paper_trading_reports"

    report_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaperTradingPlanRecord(Base):
    __tablename__ = "paper_trading_plans"

    plan_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    signal_id = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaperVsBacktestComparisonRecord(Base):
    __tablename__ = "paper_vs_backtest_comparisons"

    comparison_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyRegistryRecord(Base):
    __tablename__ = "strategy_registry"

    registry_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    lifecycle_state = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyVersionRecord(Base):
    __tablename__ = "strategy_versions"

    version_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    code_hash = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StrategyLifecycleDecisionRecord(Base):
    __tablename__ = "strategy_lifecycle_decisions"

    decision_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StrategySimilarityRecord(Base):
    __tablename__ = "strategy_similarity_results"

    similarity_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    compared_strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TradeRecordRow(Base):
    __tablename__ = "trades"

    trade_id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TradeSummaryRecord(Base):
    __tablename__ = "trade_summaries"

    strategy_id = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EnhancedReviewMetricsRecord(Base):
    __tablename__ = "enhanced_review_metrics"

    strategy_id = Column(String, primary_key=True)
    signal_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PromptLogRecord(Base):
    __tablename__ = "prompt_logs"

    prompt_id = Column(String, primary_key=True)
    agent = Column(String, index=True, nullable=False)
    model = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ModelResponseLogRecord(Base):
    __tablename__ = "model_response_logs"

    response_id = Column(String, primary_key=True)
    prompt_id = Column(String, index=True, nullable=False)
    agent = Column(String, index=True, nullable=False)
    model = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PortfolioRiskReportRecord(Base):
    __tablename__ = "portfolio_risk_reports"

    report_id = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResourceBudgetReportRecord(Base):
    __tablename__ = "resource_budget_reports"

    report_id = Column(String, primary_key=True)
    candidate_id = Column(String, index=True, nullable=False)
    strategy_id = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def _dump(model: BaseModel) -> str:
    return model.model_dump_json()


def _load(model_cls: Type[ModelT], payload: str) -> ModelT:
    return model_cls.model_validate_json(payload)


class QuantRepository:
    """SQLAlchemy-backed persistence boundary for MVP agent artifacts."""

    def __init__(self, database_url: str = "sqlite+pysqlite:///:memory:") -> None:
        self.engine = create_engine(database_url)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def save_signal(self, signal: MarketSignal) -> MarketSignal:
        with self._session() as session:
            session.merge(SignalRecord(signal_id=signal.signal_id, payload=_dump(signal)))
        return signal

    def save_research_thesis(self, thesis: ResearchThesis) -> ResearchThesis:
        with self._session() as session:
            session.merge(
                ResearchThesisRecord(
                    thesis_id=thesis.thesis_id,
                    status=thesis.status.value,
                    payload=_dump(thesis),
                )
            )
        return thesis

    def get_research_thesis(self, thesis_id: str) -> Optional[ResearchThesis]:
        record = self._get(ResearchThesisRecord, thesis_id)
        return None if record is None else _load(ResearchThesis, record.payload)

    def save_thesis_pre_review(self, pre_review: ThesisPreReview) -> ThesisPreReview:
        with self._session() as session:
            session.merge(
                ThesisPreReviewRecord(
                    pre_review_id=pre_review.pre_review_id,
                    thesis_id=pre_review.thesis_id,
                    status=pre_review.status.value,
                    payload=_dump(pre_review),
                )
            )
        return pre_review

    def get_thesis_pre_review(self, pre_review_id: str) -> Optional[ThesisPreReview]:
        record = self._get(ThesisPreReviewRecord, pre_review_id)
        return None if record is None else _load(ThesisPreReview, record.payload)

    def query_thesis_pre_reviews(
        self,
        thesis_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[ThesisPreReview]:
        with self._session() as session:
            query = session.query(ThesisPreReviewRecord)
            if thesis_id is not None:
                query = query.filter(ThesisPreReviewRecord.thesis_id == thesis_id)
            records = query.order_by(ThesisPreReviewRecord.created_at.desc()).limit(limit).all()
        return [_load(ThesisPreReview, record.payload) for record in records]

    def save_research_design_draft(self, draft: ResearchDesignDraft) -> ResearchDesignDraft:
        with self._session() as session:
            session.merge(
                ResearchDesignDraftRecord(
                    design_id=draft.design_id,
                    thesis_id=draft.thesis_id,
                    pre_review_id=draft.pre_review_id,
                    payload=_dump(draft),
                )
            )
        return draft

    def get_research_design_draft(self, design_id: str) -> Optional[ResearchDesignDraft]:
        record = self._get(ResearchDesignDraftRecord, design_id)
        return None if record is None else _load(ResearchDesignDraft, record.payload)

    def query_research_design_drafts(
        self,
        thesis_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[ResearchDesignDraft]:
        with self._session() as session:
            query = session.query(ResearchDesignDraftRecord)
            if thesis_id is not None:
                query = query.filter(ResearchDesignDraftRecord.thesis_id == thesis_id)
            records = query.order_by(ResearchDesignDraftRecord.created_at.desc()).limit(limit).all()
        return [_load(ResearchDesignDraft, record.payload) for record in records]

    def save_event_episode(self, event: EventEpisode) -> EventEpisode:
        with self._session() as session:
            session.merge(
                EventEpisodeRecord(
                    event_id=event.event_id,
                    thesis_id=event.thesis_id,
                    signal_id=event.signal_id,
                    strategy_family=event.strategy_family.value,
                    payload=_dump(event),
                )
            )
        return event

    def get_event_episode(self, event_id: str) -> Optional[EventEpisode]:
        record = self._get(EventEpisodeRecord, event_id)
        return None if record is None else _load(EventEpisode, record.payload)

    def query_event_episodes(
        self,
        thesis_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        strategy_family: Optional[str] = None,
        limit: int = 20,
    ) -> list[EventEpisode]:
        with self._session() as session:
            query = session.query(EventEpisodeRecord)
            if thesis_id is not None:
                query = query.filter(EventEpisodeRecord.thesis_id == thesis_id)
            if signal_id is not None:
                query = query.filter(EventEpisodeRecord.signal_id == signal_id)
            if strategy_family is not None:
                query = query.filter(EventEpisodeRecord.strategy_family == strategy_family)
            records = query.order_by(EventEpisodeRecord.created_at.desc()).limit(limit).all()
        return [_load(EventEpisode, record.payload) for record in records]

    def save_research_asset_index_entry(
        self,
        entry: ResearchAssetIndexEntry,
    ) -> ResearchAssetIndexEntry:
        with self._session() as session:
            session.merge(
                ResearchAssetIndexRecord(
                    asset_id=entry.asset_id,
                    asset_type=entry.asset_type,
                    signal_id=entry.signal_id,
                    strategy_id=entry.strategy_id,
                    thesis_id=entry.thesis_id,
                    payload=_dump(entry),
                )
            )
        return entry

    def get_research_asset_index_entry(
        self,
        asset_id: str,
    ) -> Optional[ResearchAssetIndexEntry]:
        record = self._get(ResearchAssetIndexRecord, asset_id)
        return None if record is None else _load(ResearchAssetIndexEntry, record.payload)

    def query_research_asset_index(
        self,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        thesis_id: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 20,
    ) -> list[ResearchAssetIndexEntry]:
        with self._session() as session:
            query = session.query(ResearchAssetIndexRecord)
            if signal_id is not None:
                query = query.filter(ResearchAssetIndexRecord.signal_id == signal_id)
            if strategy_id is not None:
                query = query.filter(ResearchAssetIndexRecord.strategy_id == strategy_id)
            if thesis_id is not None:
                query = query.filter(ResearchAssetIndexRecord.thesis_id == thesis_id)
            records = query.order_by(ResearchAssetIndexRecord.created_at.desc()).limit(limit).all()
        entries = [_load(ResearchAssetIndexEntry, record.payload) for record in records]
        if tag is not None:
            entries = [entry for entry in entries if tag in entry.tags]
        return entries

    def save_ohlcv(self, dataset_id: str, symbol: str, candles: list[OhlcvCandle]) -> list[OhlcvCandle]:
        payload = "[" + ",".join(_dump(candle) for candle in candles) + "]"
        self._save_market_data(dataset_id, "ohlcv", symbol, payload)
        return candles

    def get_ohlcv(self, dataset_id: str) -> list[OhlcvCandle]:
        record = self._get(MarketDataRecord, dataset_id)
        if record is None:
            return []
        return [OhlcvCandle.model_validate(item) for item in json.loads(record.payload)]

    def save_funding_rates(
        self,
        dataset_id: str,
        symbol: str,
        funding_rates: list[FundingRatePoint],
    ) -> list[FundingRatePoint]:
        payload = "[" + ",".join(_dump(point) for point in funding_rates) + "]"
        self._save_market_data(dataset_id, "funding_rate", symbol, payload)
        return funding_rates

    def get_funding_rates(self, dataset_id: str) -> list[FundingRatePoint]:
        record = self._get(MarketDataRecord, dataset_id)
        if record is None:
            return []
        return [FundingRatePoint.model_validate(item) for item in json.loads(record.payload)]

    def save_open_interest(
        self,
        dataset_id: str,
        symbol: str,
        open_interest: OpenInterestPoint,
    ) -> OpenInterestPoint:
        self._save_market_data(dataset_id, "open_interest", symbol, _dump(open_interest))
        return open_interest

    def get_open_interest(self, dataset_id: str) -> Optional[OpenInterestPoint]:
        record = self._get(MarketDataRecord, dataset_id)
        return None if record is None else _load(OpenInterestPoint, record.payload)

    def save_orderbook(
        self,
        dataset_id: str,
        symbol: str,
        orderbook: OrderBookSnapshot,
    ) -> OrderBookSnapshot:
        self._save_market_data(dataset_id, "orderbook", symbol, _dump(orderbook))
        return orderbook

    def get_orderbook(self, dataset_id: str) -> Optional[OrderBookSnapshot]:
        record = self._get(MarketDataRecord, dataset_id)
        return None if record is None else _load(OrderBookSnapshot, record.payload)

    def save_data_quality_report(self, report: DataQualityReport) -> DataQualityReport:
        with self._session() as session:
            session.merge(DataQualityRecord(dataset_id=report.dataset_id, payload=_dump(report)))
        return report

    def get_data_quality_report(self, dataset_id: str) -> Optional[DataQualityReport]:
        record = self._get(DataQualityRecord, dataset_id)
        return None if record is None else _load(DataQualityReport, record.payload)

    def get_signal(self, signal_id: str) -> Optional[MarketSignal]:
        record = self._get(SignalRecord, signal_id)
        return None if record is None else _load(MarketSignal, record.payload)

    def save_market_regime_snapshot(
        self,
        snapshot: MarketRegimeSnapshot,
    ) -> MarketRegimeSnapshot:
        with self._session() as session:
            session.merge(
                MarketRegimeSnapshotRecord(
                    regime_id=snapshot.regime_id,
                    signal_id=snapshot.signal_id,
                    symbol=snapshot.symbol,
                    primary_regime=snapshot.primary_regime.value,
                    payload=_dump(snapshot),
                )
            )
        return snapshot

    def get_market_regime_snapshot(self, regime_id: str) -> Optional[MarketRegimeSnapshot]:
        record = self._get(MarketRegimeSnapshotRecord, regime_id)
        return None if record is None else _load(MarketRegimeSnapshot, record.payload)

    def query_market_regime_snapshots(
        self,
        signal_id: Optional[str] = None,
        primary_regime: Optional[str] = None,
        limit: int = 20,
    ) -> list[MarketRegimeSnapshot]:
        with self._session() as session:
            query = session.query(MarketRegimeSnapshotRecord)
            if signal_id is not None:
                query = query.filter(MarketRegimeSnapshotRecord.signal_id == signal_id)
            if primary_regime is not None:
                query = query.filter(MarketRegimeSnapshotRecord.primary_regime == primary_regime)
            records = query.order_by(MarketRegimeSnapshotRecord.created_at.desc()).limit(limit).all()
            return [_load(MarketRegimeSnapshot, record.payload) for record in records]

    def save_strategy(self, strategy: StrategyManifest) -> StrategyManifest:
        with self._session() as session:
            session.merge(
                StrategyRecord(
                    strategy_id=strategy.strategy_id,
                    signal_id=strategy.signal_id,
                    payload=_dump(strategy),
                )
            )
        return strategy

    def get_strategy(self, strategy_id: str) -> Optional[StrategyManifest]:
        record = self._get(StrategyRecord, strategy_id)
        return None if record is None else _load(StrategyManifest, record.payload)

    def save_risk_audit(self, risk_audit: RiskAuditResult) -> RiskAuditResult:
        with self._session() as session:
            session.merge(
                RiskAuditRecord(strategy_id=risk_audit.strategy_id, payload=_dump(risk_audit))
            )
        return risk_audit

    def get_risk_audit(self, strategy_id: str) -> Optional[RiskAuditResult]:
        record = self._get(RiskAuditRecord, strategy_id)
        return None if record is None else _load(RiskAuditResult, record.payload)

    def save_backtest(self, backtest: BacktestReport) -> BacktestReport:
        with self._session() as session:
            session.merge(
                BacktestRecord(
                    backtest_id=backtest.backtest_id,
                    strategy_id=backtest.strategy_id,
                    payload=_dump(backtest),
                )
            )
        return backtest

    def get_backtest(self, backtest_id: str) -> Optional[BacktestReport]:
        record = self._get(BacktestRecord, backtest_id)
        return None if record is None else _load(BacktestReport, record.payload)

    def save_backtest_validation(
        self,
        validation: BacktestValidationReport,
    ) -> BacktestValidationReport:
        with self._session() as session:
            session.merge(
                BacktestValidationRecord(
                    validation_id=validation.validation_id,
                    strategy_id=validation.strategy_id,
                    payload=_dump(validation),
                )
            )
        return validation

    def get_backtest_validation(self, validation_id: str) -> Optional[BacktestValidationReport]:
        record = self._get(BacktestValidationRecord, validation_id)
        return None if record is None else _load(BacktestValidationReport, record.payload)

    def save_experiment_manifest(self, manifest: ExperimentManifest) -> ExperimentManifest:
        with self._session() as session:
            session.merge(
                ExperimentManifestRecord(
                    experiment_id=manifest.experiment_id,
                    thesis_id=manifest.thesis_id,
                    signal_id=manifest.signal_id,
                    strategy_id=manifest.strategy_id,
                    backtest_id=manifest.backtest_id,
                    payload=_dump(manifest),
                )
            )
        return manifest

    def get_experiment_manifest(self, experiment_id: str) -> Optional[ExperimentManifest]:
        record = self._get(ExperimentManifestRecord, experiment_id)
        return None if record is None else _load(ExperimentManifest, record.payload)

    def query_experiment_manifests(
        self,
        thesis_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[ExperimentManifest]:
        with self._session() as session:
            query = session.query(ExperimentManifestRecord)
            if thesis_id is not None:
                query = query.filter(ExperimentManifestRecord.thesis_id == thesis_id)
            if signal_id is not None:
                query = query.filter(ExperimentManifestRecord.signal_id == signal_id)
            if strategy_id is not None:
                query = query.filter(ExperimentManifestRecord.strategy_id == strategy_id)
            records = query.order_by(ExperimentManifestRecord.created_at.desc()).limit(limit).all()
            return [_load(ExperimentManifest, record.payload) for record in records]

    def save_experiment_queue_item(self, item: ExperimentQueueItem) -> ExperimentQueueItem:
        with self._session() as session:
            session.merge(
                ExperimentQueueRecord(
                    queue_id=item.queue_id,
                    status=item.status.value,
                    signal_id=item.signal_id,
                    strategy_id=item.strategy_id,
                    candidate_id=item.candidate_id,
                    payload=_dump(item),
                )
            )
        return item

    def get_experiment_queue_item(self, queue_id: str) -> Optional[ExperimentQueueItem]:
        record = self._get(ExperimentQueueRecord, queue_id)
        return None if record is None else _load(ExperimentQueueItem, record.payload)

    def query_experiment_queue(
        self,
        status: Optional[str] = None,
        signal_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[ExperimentQueueItem]:
        with self._session() as session:
            query = session.query(ExperimentQueueRecord)
            if status is not None:
                query = query.filter(ExperimentQueueRecord.status == status)
            if signal_id is not None:
                query = query.filter(ExperimentQueueRecord.signal_id == signal_id)
            records = query.order_by(ExperimentQueueRecord.created_at.desc()).limit(limit).all()
            return [_load(ExperimentQueueItem, record.payload) for record in records]

    def save_baseline_comparison(
        self,
        report: BaselineComparisonReport,
    ) -> BaselineComparisonReport:
        with self._session() as session:
            session.merge(
                BaselineComparisonRecord(
                    report_id=report.report_id,
                    strategy_id=report.strategy_id,
                    signal_id=report.signal_id,
                    source_backtest_id=report.source_backtest_id,
                    payload=_dump(report),
                )
            )
        return report

    def get_baseline_comparison(self, report_id: str) -> Optional[BaselineComparisonReport]:
        record = self._get(BaselineComparisonRecord, report_id)
        return None if record is None else _load(BaselineComparisonReport, record.payload)

    def query_baseline_comparisons(
        self,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[BaselineComparisonReport]:
        with self._session() as session:
            query = session.query(BaselineComparisonRecord)
            if signal_id is not None:
                query = query.filter(BaselineComparisonRecord.signal_id == signal_id)
            if strategy_id is not None:
                query = query.filter(BaselineComparisonRecord.strategy_id == strategy_id)
            records = query.order_by(BaselineComparisonRecord.created_at.desc()).limit(limit).all()
            return [_load(BaselineComparisonReport, record.payload) for record in records]

    def save_robustness_report(self, report: RobustnessReport) -> RobustnessReport:
        with self._session() as session:
            session.merge(
                RobustnessReportRecord(
                    report_id=report.report_id,
                    strategy_id=report.strategy_id,
                    source_backtest_id=report.source_backtest_id,
                    payload=_dump(report),
                )
            )
        return report

    def get_robustness_report(self, report_id: str) -> Optional[RobustnessReport]:
        record = self._get(RobustnessReportRecord, report_id)
        return None if record is None else _load(RobustnessReport, record.payload)

    def query_robustness_reports(
        self,
        strategy_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[RobustnessReport]:
        with self._session() as session:
            query = session.query(RobustnessReportRecord)
            if strategy_id is not None:
                query = query.filter(RobustnessReportRecord.strategy_id == strategy_id)
            records = query.order_by(RobustnessReportRecord.created_at.desc()).limit(limit).all()
            return [_load(RobustnessReport, record.payload) for record in records]

    def save_cross_symbol_validation(
        self,
        report: CrossSymbolValidationReport,
    ) -> CrossSymbolValidationReport:
        with self._session() as session:
            session.merge(
                CrossSymbolValidationRecord(
                    report_id=report.report_id,
                    strategy_id=report.strategy_id,
                    source_backtest_id=report.source_backtest_id,
                    payload=_dump(report),
                )
            )
        return report

    def get_cross_symbol_validation(
        self,
        report_id: str,
    ) -> Optional[CrossSymbolValidationReport]:
        record = self._get(CrossSymbolValidationRecord, report_id)
        return None if record is None else _load(CrossSymbolValidationReport, record.payload)

    def query_cross_symbol_validations(
        self,
        strategy_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[CrossSymbolValidationReport]:
        with self._session() as session:
            query = session.query(CrossSymbolValidationRecord)
            if strategy_id is not None:
                query = query.filter(CrossSymbolValidationRecord.strategy_id == strategy_id)
            records = query.order_by(CrossSymbolValidationRecord.created_at.desc()).limit(limit).all()
            return [_load(CrossSymbolValidationReport, record.payload) for record in records]

    def save_real_backtest_validation_suite(
        self,
        report: RealBacktestValidationSuiteReport,
    ) -> RealBacktestValidationSuiteReport:
        with self._session() as session:
            session.merge(
                RealBacktestValidationSuiteRecord(
                    report_id=report.report_id,
                    strategy_id=report.strategy_id,
                    source_backtest_id=report.source_backtest_id,
                    payload=_dump(report),
                )
            )
        return report

    def get_real_backtest_validation_suite(
        self,
        report_id: str,
    ) -> Optional[RealBacktestValidationSuiteReport]:
        record = self._get(RealBacktestValidationSuiteRecord, report_id)
        return None if record is None else _load(RealBacktestValidationSuiteReport, record.payload)

    def query_real_backtest_validation_suites(
        self,
        strategy_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[RealBacktestValidationSuiteReport]:
        with self._session() as session:
            query = session.query(RealBacktestValidationSuiteRecord)
            if strategy_id is not None:
                query = query.filter(RealBacktestValidationSuiteRecord.strategy_id == strategy_id)
            records = query.order_by(RealBacktestValidationSuiteRecord.created_at.desc()).limit(limit).all()
            return [_load(RealBacktestValidationSuiteReport, record.payload) for record in records]

    def save_monte_carlo_backtest(
        self,
        report: MonteCarloBacktestReport,
    ) -> MonteCarloBacktestReport:
        with self._session() as session:
            session.merge(
                MonteCarloBacktestRecord(
                    report_id=report.report_id,
                    strategy_id=report.strategy_id,
                    source_backtest_id=report.source_backtest_id,
                    payload=_dump(report),
                )
            )
        return report

    def get_monte_carlo_backtest(
        self,
        report_id: str,
    ) -> Optional[MonteCarloBacktestReport]:
        record = self._get(MonteCarloBacktestRecord, report_id)
        return None if record is None else _load(MonteCarloBacktestReport, record.payload)

    def save_review(self, review: ReviewCase) -> ReviewCase:
        with self._session() as session:
            session.merge(
                ReviewRecord(
                    case_id=review.case_id,
                    strategy_id=review.strategy_id,
                    signal_id=review.signal_id,
                    result=review.result.value,
                    payload=_dump(review),
                )
            )
        return review

    def get_review(self, case_id: str) -> Optional[ReviewCase]:
        record = self._get(ReviewRecord, case_id)
        return None if record is None else _load(ReviewCase, record.payload)

    def query_reviews(
        self,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        result: Optional[str] = None,
    ) -> list[ReviewCase]:
        with self._session() as session:
            query = session.query(ReviewRecord)
            if signal_id is not None:
                query = query.filter(ReviewRecord.signal_id == signal_id)
            if strategy_id is not None:
                query = query.filter(ReviewRecord.strategy_id == strategy_id)
            if result is not None:
                query = query.filter(ReviewRecord.result == result)
            return [_load(ReviewCase, record.payload) for record in query.all()]

    def save_review_session(self, session_model: ReviewSession) -> ReviewSession:
        with self._session() as session:
            session.merge(
                ReviewSessionRecord(
                    session_id=session_model.session_id,
                    thesis_id=session_model.thesis_id,
                    signal_id=session_model.signal_id,
                    strategy_id=session_model.strategy_id,
                    payload=_dump(session_model),
                )
            )
        return session_model

    def get_review_session(self, session_id: str) -> Optional[ReviewSession]:
        record = self._get(ReviewSessionRecord, session_id)
        return None if record is None else _load(ReviewSession, record.payload)

    def query_review_sessions(
        self,
        thesis_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[ReviewSession]:
        with self._session() as session:
            query = session.query(ReviewSessionRecord)
            if thesis_id is not None:
                query = query.filter(ReviewSessionRecord.thesis_id == thesis_id)
            if signal_id is not None:
                query = query.filter(ReviewSessionRecord.signal_id == signal_id)
            if strategy_id is not None:
                query = query.filter(ReviewSessionRecord.strategy_id == strategy_id)
            records = query.order_by(ReviewSessionRecord.created_at.desc()).limit(limit).all()
        return [_load(ReviewSession, record.payload) for record in records]

    def save_negative_result_case(self, case: NegativeResultCase) -> NegativeResultCase:
        with self._session() as session:
            session.merge(
                NegativeResultRecord(
                    case_id=case.case_id,
                    signal_id=case.signal_id,
                    strategy_id=case.strategy_id,
                    candidate_id=case.candidate_id,
                    payload=_dump(case),
                )
            )
        return case

    def get_negative_result_case(self, case_id: str) -> Optional[NegativeResultCase]:
        record = self._get(NegativeResultRecord, case_id)
        return None if record is None else _load(NegativeResultCase, record.payload)

    def query_negative_result_cases(
        self,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[NegativeResultCase]:
        with self._session() as session:
            query = session.query(NegativeResultRecord)
            if signal_id is not None:
                query = query.filter(NegativeResultRecord.signal_id == signal_id)
            if strategy_id is not None:
                query = query.filter(NegativeResultRecord.strategy_id == strategy_id)
            records = query.order_by(NegativeResultRecord.created_at.desc()).limit(limit).all()
            return [_load(NegativeResultCase, record.payload) for record in records]

    def save_research_finding(self, finding: ResearchFinding) -> ResearchFinding:
        with self._session() as session:
            session.merge(
                ResearchFindingRecord(
                    finding_id=finding.finding_id,
                    signal_id=finding.signal_id,
                    strategy_id=finding.strategy_id,
                    thesis_id=finding.thesis_id,
                    finding_type=finding.finding_type,
                    severity=finding.severity.value,
                    payload=_dump(finding),
                )
            )
        return finding

    def get_research_finding(self, finding_id: str) -> Optional[ResearchFinding]:
        record = self._get(ResearchFindingRecord, finding_id)
        return None if record is None else _load(ResearchFinding, record.payload)

    def query_research_findings(
        self,
        thesis_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 20,
    ) -> list[ResearchFinding]:
        with self._session() as session:
            query = session.query(ResearchFindingRecord)
            if thesis_id is not None:
                query = query.filter(ResearchFindingRecord.thesis_id == thesis_id)
            if signal_id is not None:
                query = query.filter(ResearchFindingRecord.signal_id == signal_id)
            if strategy_id is not None:
                query = query.filter(ResearchFindingRecord.strategy_id == strategy_id)
            if severity is not None:
                query = query.filter(ResearchFindingRecord.severity == severity)
            records = query.order_by(ResearchFindingRecord.created_at.desc()).limit(limit).all()
            return [_load(ResearchFinding, record.payload) for record in records]

    def save_research_task(self, task: ResearchTask) -> ResearchTask:
        with self._session() as session:
            session.merge(
                ResearchTaskRecord(
                    task_id=task.task_id,
                    task_type=task.task_type.value,
                    subject_type=task.subject_type,
                    subject_id=task.subject_id,
                    signal_id=task.signal_id,
                    strategy_id=task.strategy_id,
                    thesis_id=task.thesis_id,
                    status=task.status.value,
                    payload=_dump(task),
                )
            )
        return task

    def get_research_task(self, task_id: str) -> Optional[ResearchTask]:
        record = self._get(ResearchTaskRecord, task_id)
        return None if record is None else _load(ResearchTask, record.payload)

    def query_research_tasks(
        self,
        thesis_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[ResearchTask]:
        with self._session() as session:
            query = session.query(ResearchTaskRecord)
            if thesis_id is not None:
                query = query.filter(ResearchTaskRecord.thesis_id == thesis_id)
            if signal_id is not None:
                query = query.filter(ResearchTaskRecord.signal_id == signal_id)
            if strategy_id is not None:
                query = query.filter(ResearchTaskRecord.strategy_id == strategy_id)
            if task_type is not None:
                query = query.filter(ResearchTaskRecord.task_type == task_type)
            if status is not None:
                query = query.filter(ResearchTaskRecord.status == status)
            records = query.order_by(ResearchTaskRecord.created_at.desc()).limit(limit).all()
            return [_load(ResearchTask, record.payload) for record in records]

    def save_research_harness_cycle(self, cycle: ResearchHarnessCycle) -> ResearchHarnessCycle:
        with self._session() as session:
            session.merge(
                ResearchHarnessCycleRecord(
                    cycle_id=cycle.cycle_id,
                    signal_id=cycle.signal_id,
                    thesis_id=cycle.thesis_id,
                    source=cycle.source,
                    payload=_dump(cycle),
                )
            )
        return cycle

    def get_research_harness_cycle(self, cycle_id: str) -> Optional[ResearchHarnessCycle]:
        record = self._get(ResearchHarnessCycleRecord, cycle_id)
        return None if record is None else _load(ResearchHarnessCycle, record.payload)

    def query_research_harness_cycles(
        self,
        thesis_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[ResearchHarnessCycle]:
        with self._session() as session:
            query = session.query(ResearchHarnessCycleRecord)
            if thesis_id is not None:
                query = query.filter(ResearchHarnessCycleRecord.thesis_id == thesis_id)
            if signal_id is not None:
                query = query.filter(ResearchHarnessCycleRecord.signal_id == signal_id)
            records = query.order_by(ResearchHarnessCycleRecord.created_at.desc()).limit(limit).all()
            return [_load(ResearchHarnessCycle, record.payload) for record in records]

    def save_event_definition_sensitivity_report(
        self,
        report: EventDefinitionSensitivityReport,
    ) -> EventDefinitionSensitivityReport:
        with self._session() as session:
            session.merge(
                EventDefinitionSensitivityReportRecord(
                    report_id=report.report_id,
                    task_id=report.task_id,
                    signal_id=report.signal_id,
                    strategy_id=report.strategy_id,
                    thesis_id=report.thesis_id,
                    strategy_family=report.strategy_family,
                    symbol=report.symbol,
                    payload=_dump(report),
                )
            )
        return report

    def get_event_definition_sensitivity_report(
        self,
        report_id: str,
    ) -> Optional[EventDefinitionSensitivityReport]:
        record = self._get(EventDefinitionSensitivityReportRecord, report_id)
        return None if record is None else _load(EventDefinitionSensitivityReport, record.payload)

    def query_event_definition_sensitivity_reports(
        self,
        task_id: Optional[str] = None,
        thesis_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        strategy_family: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 20,
    ) -> list[EventDefinitionSensitivityReport]:
        with self._session() as session:
            query = session.query(EventDefinitionSensitivityReportRecord)
            if task_id is not None:
                query = query.filter(EventDefinitionSensitivityReportRecord.task_id == task_id)
            if thesis_id is not None:
                query = query.filter(EventDefinitionSensitivityReportRecord.thesis_id == thesis_id)
            if signal_id is not None:
                query = query.filter(EventDefinitionSensitivityReportRecord.signal_id == signal_id)
            if strategy_family is not None:
                query = query.filter(EventDefinitionSensitivityReportRecord.strategy_family == strategy_family)
            if symbol is not None:
                query = query.filter(EventDefinitionSensitivityReportRecord.symbol == symbol)
            records = query.order_by(EventDefinitionSensitivityReportRecord.created_at.desc()).limit(limit).all()
            return [_load(EventDefinitionSensitivityReport, record.payload) for record in records]

    def save_event_definition_universe_report(
        self,
        report: EventDefinitionUniverseReport,
    ) -> EventDefinitionUniverseReport:
        with self._session() as session:
            session.merge(
                EventDefinitionUniverseReportRecord(
                    report_id=report.report_id,
                    task_id=report.task_id,
                    signal_id=report.signal_id,
                    thesis_id=report.thesis_id,
                    strategy_family=report.strategy_family,
                    payload=_dump(report),
                )
            )
        return report

    def get_event_definition_universe_report(
        self,
        report_id: str,
    ) -> Optional[EventDefinitionUniverseReport]:
        record = self._get(EventDefinitionUniverseReportRecord, report_id)
        return None if record is None else _load(EventDefinitionUniverseReport, record.payload)

    def query_event_definition_universe_reports(
        self,
        task_id: Optional[str] = None,
        thesis_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        strategy_family: Optional[str] = None,
        limit: int = 20,
    ) -> list[EventDefinitionUniverseReport]:
        with self._session() as session:
            query = session.query(EventDefinitionUniverseReportRecord)
            if task_id is not None:
                query = query.filter(EventDefinitionUniverseReportRecord.task_id == task_id)
            if thesis_id is not None:
                query = query.filter(EventDefinitionUniverseReportRecord.thesis_id == thesis_id)
            if signal_id is not None:
                query = query.filter(EventDefinitionUniverseReportRecord.signal_id == signal_id)
            if strategy_family is not None:
                query = query.filter(EventDefinitionUniverseReportRecord.strategy_family == strategy_family)
            records = query.order_by(EventDefinitionUniverseReportRecord.created_at.desc()).limit(limit).all()
            return [_load(EventDefinitionUniverseReport, record.payload) for record in records]

    def save_failed_breakout_sensitivity_report(
        self,
        report: FailedBreakoutSensitivityReport,
    ) -> FailedBreakoutSensitivityReport:
        with self._session() as session:
            session.merge(
                FailedBreakoutSensitivityReportRecord(
                    report_id=report.report_id,
                    task_id=report.task_id,
                    signal_id=report.signal_id,
                    strategy_id=report.strategy_id,
                    thesis_id=report.thesis_id,
                    strategy_family=report.strategy_family,
                    symbol=report.symbol,
                    payload=_dump(report),
                )
            )
        return report

    def get_failed_breakout_sensitivity_report(
        self,
        report_id: str,
    ) -> Optional[FailedBreakoutSensitivityReport]:
        record = self._get(FailedBreakoutSensitivityReportRecord, report_id)
        return None if record is None else _load(FailedBreakoutSensitivityReport, record.payload)

    def query_failed_breakout_sensitivity_reports(
        self,
        task_id: Optional[str] = None,
        thesis_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        strategy_family: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 20,
    ) -> list[FailedBreakoutSensitivityReport]:
        with self._session() as session:
            query = session.query(FailedBreakoutSensitivityReportRecord)
            if task_id is not None:
                query = query.filter(FailedBreakoutSensitivityReportRecord.task_id == task_id)
            if thesis_id is not None:
                query = query.filter(FailedBreakoutSensitivityReportRecord.thesis_id == thesis_id)
            if signal_id is not None:
                query = query.filter(FailedBreakoutSensitivityReportRecord.signal_id == signal_id)
            if strategy_family is not None:
                query = query.filter(FailedBreakoutSensitivityReportRecord.strategy_family == strategy_family)
            if symbol is not None:
                query = query.filter(FailedBreakoutSensitivityReportRecord.symbol == symbol)
            records = query.order_by(FailedBreakoutSensitivityReportRecord.created_at.desc()).limit(limit).all()
            return [_load(FailedBreakoutSensitivityReport, record.payload) for record in records]

    def save_failed_breakout_universe_report(
        self,
        report: FailedBreakoutUniverseReport,
    ) -> FailedBreakoutUniverseReport:
        with self._session() as session:
            session.merge(
                FailedBreakoutUniverseReportRecord(
                    report_id=report.report_id,
                    task_id=report.task_id,
                    signal_id=report.signal_id,
                    thesis_id=report.thesis_id,
                    strategy_family=report.strategy_family,
                    payload=_dump(report),
                )
            )
        return report

    def get_failed_breakout_universe_report(
        self,
        report_id: str,
    ) -> Optional[FailedBreakoutUniverseReport]:
        record = self._get(FailedBreakoutUniverseReportRecord, report_id)
        return None if record is None else _load(FailedBreakoutUniverseReport, record.payload)

    def query_failed_breakout_universe_reports(
        self,
        task_id: Optional[str] = None,
        thesis_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        strategy_family: Optional[str] = None,
        limit: int = 20,
    ) -> list[FailedBreakoutUniverseReport]:
        with self._session() as session:
            query = session.query(FailedBreakoutUniverseReportRecord)
            if task_id is not None:
                query = query.filter(FailedBreakoutUniverseReportRecord.task_id == task_id)
            if thesis_id is not None:
                query = query.filter(FailedBreakoutUniverseReportRecord.thesis_id == thesis_id)
            if signal_id is not None:
                query = query.filter(FailedBreakoutUniverseReportRecord.signal_id == signal_id)
            if strategy_family is not None:
                query = query.filter(FailedBreakoutUniverseReportRecord.strategy_family == strategy_family)
            records = query.order_by(FailedBreakoutUniverseReportRecord.created_at.desc()).limit(limit).all()
            return [_load(FailedBreakoutUniverseReport, record.payload) for record in records]

    def save_strategy_family_walk_forward_report(
        self,
        report: StrategyFamilyWalkForwardReport,
    ) -> StrategyFamilyWalkForwardReport:
        with self._session() as session:
            session.merge(
                StrategyFamilyWalkForwardReportRecord(
                    report_id=report.report_id,
                    strategy_family=report.strategy_family,
                    source_universe_report_id=report.source_universe_report_id,
                    payload=_dump(report),
                )
            )
        return report

    def get_strategy_family_walk_forward_report(
        self,
        report_id: str,
    ) -> Optional[StrategyFamilyWalkForwardReport]:
        record = self._get(StrategyFamilyWalkForwardReportRecord, report_id)
        return None if record is None else _load(StrategyFamilyWalkForwardReport, record.payload)

    def query_strategy_family_walk_forward_reports(
        self,
        strategy_family: Optional[str] = None,
        source_universe_report_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[StrategyFamilyWalkForwardReport]:
        with self._session() as session:
            query = session.query(StrategyFamilyWalkForwardReportRecord)
            if strategy_family is not None:
                query = query.filter(StrategyFamilyWalkForwardReportRecord.strategy_family == strategy_family)
            if source_universe_report_id is not None:
                query = query.filter(
                    StrategyFamilyWalkForwardReportRecord.source_universe_report_id == source_universe_report_id
                )
            records = query.order_by(StrategyFamilyWalkForwardReportRecord.created_at.desc()).limit(limit).all()
            return [_load(StrategyFamilyWalkForwardReport, record.payload) for record in records]

    def save_strategy_family_monte_carlo_report(
        self,
        report: StrategyFamilyMonteCarloReport,
    ) -> StrategyFamilyMonteCarloReport:
        with self._session() as session:
            session.merge(
                StrategyFamilyMonteCarloReportRecord(
                    report_id=report.report_id,
                    strategy_family=report.strategy_family,
                    source_universe_report_id=report.source_universe_report_id,
                    payload=_dump(report),
                )
            )
        return report

    def get_strategy_family_monte_carlo_report(
        self,
        report_id: str,
    ) -> Optional[StrategyFamilyMonteCarloReport]:
        record = self._get(StrategyFamilyMonteCarloReportRecord, report_id)
        return None if record is None else _load(StrategyFamilyMonteCarloReport, record.payload)

    def query_strategy_family_monte_carlo_reports(
        self,
        strategy_family: Optional[str] = None,
        source_universe_report_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[StrategyFamilyMonteCarloReport]:
        with self._session() as session:
            query = session.query(StrategyFamilyMonteCarloReportRecord)
            if strategy_family is not None:
                query = query.filter(StrategyFamilyMonteCarloReportRecord.strategy_family == strategy_family)
            if source_universe_report_id is not None:
                query = query.filter(
                    StrategyFamilyMonteCarloReportRecord.source_universe_report_id == source_universe_report_id
                )
            records = query.order_by(StrategyFamilyMonteCarloReportRecord.created_at.desc()).limit(limit).all()
            return [_load(StrategyFamilyMonteCarloReport, record.payload) for record in records]

    def save_workflow_run(self, workflow: WorkflowRun) -> WorkflowRun:
        with self._session() as session:
            session.merge(
                WorkflowRunRecord(
                    workflow_run_id=workflow.workflow_run_id,
                    signal_id=workflow.signal_id,
                    strategy_id=workflow.strategy_id,
                    state=workflow.state.value,
                    payload=_dump(workflow),
                )
            )
        return workflow

    def get_workflow_run(self, workflow_run_id: str) -> Optional[WorkflowRun]:
        record = self._get(WorkflowRunRecord, workflow_run_id)
        return None if record is None else _load(WorkflowRun, record.payload)

    def save_paper_portfolio(self, portfolio: PaperPortfolio) -> PaperPortfolio:
        with self._session() as session:
            session.merge(
                PaperPortfolioRecord(portfolio_id=portfolio.portfolio_id, payload=_dump(portfolio))
            )
        return portfolio

    def get_paper_portfolio(self, portfolio_id: str) -> Optional[PaperPortfolio]:
        record = self._get(PaperPortfolioRecord, portfolio_id)
        return None if record is None else _load(PaperPortfolio, record.payload)

    def save_paper_order(self, order: PaperOrder) -> PaperOrder:
        with self._session() as session:
            session.merge(
                PaperOrderRecord(
                    order_id=order.order_id,
                    strategy_id=order.strategy_id,
                    payload=_dump(order),
                )
            )
        return order

    def get_paper_order(self, order_id: str) -> Optional[PaperOrder]:
        record = self._get(PaperOrderRecord, order_id)
        return None if record is None else _load(PaperOrder, record.payload)

    def save_paper_fill(self, fill: PaperFill) -> PaperFill:
        with self._session() as session:
            session.merge(
                PaperFillRecord(
                    fill_id=fill.fill_id,
                    order_id=fill.order_id,
                    strategy_id=fill.strategy_id,
                    payload=_dump(fill),
                )
            )
        return fill

    def get_paper_fill(self, fill_id: str) -> Optional[PaperFill]:
        record = self._get(PaperFillRecord, fill_id)
        return None if record is None else _load(PaperFill, record.payload)

    def save_paper_position(self, position: PaperPosition) -> PaperPosition:
        with self._session() as session:
            session.merge(
                PaperPositionRecord(
                    position_id=position.position_id,
                    strategy_id=position.strategy_id,
                    payload=_dump(position),
                )
            )
        return position

    def get_paper_position(self, position_id: str) -> Optional[PaperPosition]:
        record = self._get(PaperPositionRecord, position_id)
        return None if record is None else _load(PaperPosition, record.payload)

    def save_paper_trading_report(self, report: PaperTradingReport) -> PaperTradingReport:
        with self._session() as session:
            session.merge(
                PaperTradingReportRecord(
                    report_id=report.report_id,
                    strategy_id=report.strategy_id,
                    payload=_dump(report),
                )
            )
        return report

    def get_paper_trading_report(self, report_id: str) -> Optional[PaperTradingReport]:
        record = self._get(PaperTradingReportRecord, report_id)
        return None if record is None else _load(PaperTradingReport, record.payload)

    def save_paper_trading_plan(self, plan: PaperTradingPlan) -> PaperTradingPlan:
        with self._session() as session:
            session.merge(
                PaperTradingPlanRecord(
                    plan_id=plan.plan_id,
                    strategy_id=plan.strategy_id,
                    signal_id=plan.signal_id,
                    status=plan.status.value,
                    payload=_dump(plan),
                )
            )
        return plan

    def get_paper_trading_plan(self, plan_id: str) -> Optional[PaperTradingPlan]:
        record = self._get(PaperTradingPlanRecord, plan_id)
        return None if record is None else _load(PaperTradingPlan, record.payload)

    def query_paper_trading_plans(
        self,
        status: Optional[str] = None,
        signal_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[PaperTradingPlan]:
        with self._session() as session:
            query = session.query(PaperTradingPlanRecord)
            if status is not None:
                query = query.filter(PaperTradingPlanRecord.status == status)
            if signal_id is not None:
                query = query.filter(PaperTradingPlanRecord.signal_id == signal_id)
            records = query.order_by(PaperTradingPlanRecord.created_at.desc()).limit(limit).all()
            return [_load(PaperTradingPlan, record.payload) for record in records]

    def save_paper_vs_backtest_comparison(
        self,
        comparison: PaperVsBacktestComparison,
    ) -> PaperVsBacktestComparison:
        with self._session() as session:
            session.merge(
                PaperVsBacktestComparisonRecord(
                    comparison_id=comparison.comparison_id,
                    strategy_id=comparison.strategy_id,
                    payload=_dump(comparison),
                )
            )
        return comparison

    def get_paper_vs_backtest_comparison(
        self,
        comparison_id: str,
    ) -> Optional[PaperVsBacktestComparison]:
        record = self._get(PaperVsBacktestComparisonRecord, comparison_id)
        return None if record is None else _load(PaperVsBacktestComparison, record.payload)

    def save_strategy_registry_entry(
        self,
        entry: StrategyRegistryEntry,
    ) -> StrategyRegistryEntry:
        with self._session() as session:
            session.merge(
                StrategyRegistryRecord(
                    registry_id=entry.registry_id,
                    strategy_id=entry.strategy_id,
                    lifecycle_state=entry.lifecycle_state.value,
                    payload=_dump(entry),
                )
            )
        return entry

    def get_strategy_registry_entry(self, registry_id: str) -> Optional[StrategyRegistryEntry]:
        record = self._get(StrategyRegistryRecord, registry_id)
        return None if record is None else _load(StrategyRegistryEntry, record.payload)

    def save_strategy_version(self, version: StrategyVersion) -> StrategyVersion:
        with self._session() as session:
            session.merge(
                StrategyVersionRecord(
                    version_id=version.version_id,
                    strategy_id=version.strategy_id,
                    code_hash=version.code_hash,
                    payload=_dump(version),
                )
            )
        return version

    def get_strategy_version(self, version_id: str) -> Optional[StrategyVersion]:
        record = self._get(StrategyVersionRecord, version_id)
        return None if record is None else _load(StrategyVersion, record.payload)

    def save_strategy_lifecycle_decision(
        self,
        decision: StrategyLifecycleDecision,
    ) -> StrategyLifecycleDecision:
        decision_id = (
            f"{decision.strategy_id}:{decision.from_state.value}:{decision.to_state.value}:"
            f"{int(decision.created_at.timestamp() * 1000)}"
        )
        with self._session() as session:
            session.merge(
                StrategyLifecycleDecisionRecord(
                    decision_id=decision_id,
                    strategy_id=decision.strategy_id,
                    payload=_dump(decision),
                )
            )
        return decision

    def save_strategy_similarity_result(
        self,
        similarity: StrategySimilarityResult,
    ) -> StrategySimilarityResult:
        similarity_id = f"{similarity.strategy_id}:{similarity.compared_strategy_id}"
        with self._session() as session:
            session.merge(
                StrategySimilarityRecord(
                    similarity_id=similarity_id,
                    strategy_id=similarity.strategy_id,
                    compared_strategy_id=similarity.compared_strategy_id,
                    payload=_dump(similarity),
                )
            )
        return similarity

    def save_trade(self, trade: TradeRecord) -> TradeRecord:
        with self._session() as session:
            session.merge(
                TradeRecordRow(
                    trade_id=trade.trade_id,
                    strategy_id=trade.strategy_id,
                    symbol=trade.symbol,
                    payload=_dump(trade),
                )
            )
        return trade

    def get_trade(self, trade_id: str) -> Optional[TradeRecord]:
        record = self._get(TradeRecordRow, trade_id)
        return None if record is None else _load(TradeRecord, record.payload)

    def save_trade_summary(self, summary: TradeSummary) -> TradeSummary:
        with self._session() as session:
            session.merge(TradeSummaryRecord(strategy_id=summary.strategy_id, payload=_dump(summary)))
        return summary

    def get_trade_summary(self, strategy_id: str) -> Optional[TradeSummary]:
        record = self._get(TradeSummaryRecord, strategy_id)
        return None if record is None else _load(TradeSummary, record.payload)

    def save_enhanced_review_metrics(
        self,
        metrics: EnhancedReviewMetrics,
    ) -> EnhancedReviewMetrics:
        with self._session() as session:
            session.merge(
                EnhancedReviewMetricsRecord(
                    strategy_id=metrics.strategy_id,
                    signal_id=metrics.signal_id,
                    payload=_dump(metrics),
                )
            )
        return metrics

    def get_enhanced_review_metrics(self, strategy_id: str) -> Optional[EnhancedReviewMetrics]:
        record = self._get(EnhancedReviewMetricsRecord, strategy_id)
        return None if record is None else _load(EnhancedReviewMetrics, record.payload)

    def query_enhanced_review_metrics(
        self,
        signal_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[EnhancedReviewMetrics]:
        with self._session() as session:
            query = session.query(EnhancedReviewMetricsRecord)
            if signal_id is not None:
                query = query.filter(EnhancedReviewMetricsRecord.signal_id == signal_id)
            records = query.order_by(EnhancedReviewMetricsRecord.created_at.desc()).limit(limit).all()
            return [_load(EnhancedReviewMetrics, record.payload) for record in records]

    def save_prompt_log(self, prompt_log: PromptLog) -> PromptLog:
        with self._session() as session:
            session.merge(
                PromptLogRecord(
                    prompt_id=prompt_log.prompt_id,
                    agent=prompt_log.agent,
                    model=prompt_log.model,
                    payload=_dump(prompt_log),
                )
            )
        return prompt_log

    def get_prompt_log(self, prompt_id: str) -> Optional[PromptLog]:
        record = self._get(PromptLogRecord, prompt_id)
        return None if record is None else _load(PromptLog, record.payload)

    def save_model_response_log(self, response_log: ModelResponseLog) -> ModelResponseLog:
        with self._session() as session:
            session.merge(
                ModelResponseLogRecord(
                    response_id=response_log.response_id,
                    prompt_id=response_log.prompt_id,
                    agent=response_log.agent,
                    model=response_log.model,
                    payload=_dump(response_log),
                )
            )
        return response_log

    def get_model_response_log(self, response_id: str) -> Optional[ModelResponseLog]:
        record = self._get(ModelResponseLogRecord, response_id)
        return None if record is None else _load(ModelResponseLog, record.payload)

    def save_portfolio_risk_report(self, report: PortfolioRiskReport) -> PortfolioRiskReport:
        with self._session() as session:
            session.merge(PortfolioRiskReportRecord(report_id=report.report_id, payload=_dump(report)))
        return report

    def get_portfolio_risk_report(self, report_id: str) -> Optional[PortfolioRiskReport]:
        record = self._get(PortfolioRiskReportRecord, report_id)
        return None if record is None else _load(PortfolioRiskReport, record.payload)

    def save_resource_budget_report(self, report: ResourceBudgetReport) -> ResourceBudgetReport:
        with self._session() as session:
            session.merge(
                ResourceBudgetReportRecord(
                    report_id=report.report_id,
                    candidate_id=report.candidate_id,
                    strategy_id=report.strategy_id,
                    payload=_dump(report),
                )
            )
        return report

    def get_resource_budget_report(self, report_id: str) -> Optional[ResourceBudgetReport]:
        record = self._get(ResourceBudgetReportRecord, report_id)
        return None if record is None else _load(ResourceBudgetReport, record.payload)

    def query_resource_budget_reports(
        self,
        strategy_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[ResourceBudgetReport]:
        with self._session() as session:
            query = session.query(ResourceBudgetReportRecord)
            if strategy_id is not None:
                query = query.filter(ResourceBudgetReportRecord.strategy_id == strategy_id)
            records = query.order_by(ResourceBudgetReportRecord.created_at.desc()).limit(limit).all()
            return [_load(ResourceBudgetReport, record.payload) for record in records]

    def _get(self, record_cls: type[Base], primary_key: str) -> Optional[Base]:
        with self._session() as session:
            return session.get(record_cls, primary_key)

    def _session(self) -> Session:
        return self.session_factory.begin()

    def _save_market_data(self, dataset_id: str, data_type: str, symbol: str, payload: str) -> None:
        with self._session() as session:
            session.merge(
                MarketDataRecord(
                    dataset_id=dataset_id,
                    data_type=data_type,
                    symbol=symbol.upper(),
                    payload=payload,
                )
            )
