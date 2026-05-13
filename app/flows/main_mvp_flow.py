from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict

from app.models import (
    BacktestReport,
    MarketSignal,
    ReviewCase,
    RiskAuditResult,
    StrategyManifest,
    WorkflowRun,
    WorkflowState,
)
from app.services.backtester import run_mock_backtest
from app.services.researcher import generate_mock_strategy
from app.services.reviewer import build_review_case
from app.services.risk_auditor import audit_strategy_code
from app.storage import InMemoryReviewStore, QuantRepository


class MvpFlowResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    workflow: WorkflowRun
    signal: MarketSignal
    strategy: StrategyManifest
    risk_audit: RiskAuditResult
    backtest: Optional[BacktestReport]
    review: ReviewCase


def run_mvp_flow(
    signal: MarketSignal,
    review_store: Optional[InMemoryReviewStore] = None,
    repository: Optional[QuantRepository] = None,
    strategy_generator: Callable[[MarketSignal], tuple[StrategyManifest, str]] = generate_mock_strategy,
    backtest_runner: Callable[[MarketSignal, StrategyManifest], BacktestReport] = run_mock_backtest,
) -> MvpFlowResult:
    store = review_store or InMemoryReviewStore()
    if repository is not None:
        repository.save_signal(signal)

    workflow = WorkflowRun(
        workflow_run_id=f"run_{signal.signal_id}",
        signal_id=signal.signal_id,
        state=WorkflowState.NEW_SIGNAL,
    ).transition(WorkflowState.SIGNAL_VALIDATED)
    if repository is not None:
        repository.save_workflow_run(workflow)

    strategy, code = strategy_generator(signal)
    if repository is not None:
        repository.save_strategy(strategy)

    workflow = workflow.model_copy(update={"strategy_id": strategy.strategy_id}).transition(
        WorkflowState.STRATEGY_GENERATED
    )
    if repository is not None:
        repository.save_workflow_run(workflow)

    workflow = workflow.transition(WorkflowState.RISK_AUDITING)
    if repository is not None:
        repository.save_workflow_run(workflow)

    risk_audit = audit_strategy_code(code, strategy)
    if repository is not None:
        repository.save_risk_audit(risk_audit)

    if not risk_audit.approved:
        workflow = workflow.transition(WorkflowState.RISK_REJECTED)
        review = store.add(build_review_case(signal, strategy, risk_audit))
        if repository is not None:
            repository.save_workflow_run(workflow)
            repository.save_review(review)

        workflow = workflow.transition(WorkflowState.REVIEW_COMPLETED)
        if repository is not None:
            repository.save_workflow_run(workflow)

        return MvpFlowResult(
            workflow=workflow,
            signal=signal,
            strategy=strategy,
            risk_audit=risk_audit,
            backtest=None,
            review=review,
        )

    workflow = workflow.transition(WorkflowState.RISK_APPROVED)
    if repository is not None:
        repository.save_workflow_run(workflow)

    workflow = workflow.transition(WorkflowState.BACKTEST_RUNNING)
    if repository is not None:
        repository.save_workflow_run(workflow)

    backtest = backtest_runner(signal, strategy)
    if repository is not None:
        repository.save_backtest(backtest)

    workflow = workflow.transition(
        WorkflowState.BACKTEST_PASSED
        if backtest.status.value == "passed"
        else WorkflowState.BACKTEST_FAILED,
        error=backtest.error,
    )
    if repository is not None:
        repository.save_workflow_run(workflow)

    review = store.add(build_review_case(signal, strategy, risk_audit, backtest))
    if repository is not None:
        repository.save_review(review)

    workflow = workflow.transition(WorkflowState.REVIEW_COMPLETED)
    if repository is not None:
        repository.save_workflow_run(workflow)

    return MvpFlowResult(
        workflow=workflow,
        signal=signal,
        strategy=strategy,
        risk_audit=risk_audit,
        backtest=backtest,
        review=review,
    )
