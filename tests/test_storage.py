from app.flows import run_mvp_flow
from app.models import BacktestReport, BacktestStatus, WorkflowState
from app.storage import InMemoryReviewStore, QuantRepository
from tests.test_models import sample_signal


def test_repository_persists_core_artifacts() -> None:
    repository = QuantRepository()
    signal = sample_signal()
    result = run_mvp_flow(signal, repository=repository)

    assert repository.get_signal(signal.signal_id) == signal
    assert repository.get_strategy(result.strategy.strategy_id) == result.strategy
    assert repository.get_risk_audit(result.strategy.strategy_id) == result.risk_audit
    assert repository.get_backtest(result.backtest.backtest_id) == result.backtest
    assert repository.get_review(result.review.case_id) == result.review
    assert repository.get_workflow_run(result.workflow.workflow_run_id).state == WorkflowState.REVIEW_COMPLETED


def test_repository_can_filter_review_cases() -> None:
    repository = QuantRepository()
    result = run_mvp_flow(sample_signal(), repository=repository)

    reviews = repository.query_reviews(signal_id=result.signal.signal_id, result=result.review.result.value)

    assert reviews == [result.review]


def test_repository_persists_failed_backtest_reports() -> None:
    repository = QuantRepository()
    report = BacktestReport(
        backtest_id="backtest_failed_001",
        strategy_id="strategy_001",
        timerange="20240101-20260501",
        trades=0,
        win_rate=0,
        profit_factor=0,
        max_drawdown=0,
        total_return=0,
        status=BacktestStatus.FAILED,
        error="No trades were generated.",
    )

    repository.save_backtest(report)

    assert repository.get_backtest(report.backtest_id) == report


def test_in_memory_review_store_filters_cases() -> None:
    store = InMemoryReviewStore()
    result = run_mvp_flow(sample_signal(), review_store=store)

    assert store.query(strategy_id=result.strategy.strategy_id) == [result.review]
    assert store.query(strategy_id="missing") == []
