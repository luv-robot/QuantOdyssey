from app.flows import run_mvp_flow
from app.models import BacktestReport, BacktestStatus, WorkflowState
from app.services.researcher import generate_mock_strategy
from tests.test_models import sample_signal


def test_mvp_flow_completes_review_for_valid_signal() -> None:
    result = run_mvp_flow(sample_signal(rank_score=82))

    assert result.workflow.state == WorkflowState.REVIEW_COMPLETED
    assert result.risk_audit.approved is True
    assert result.backtest is not None
    assert result.review.reusable_lessons


def test_mvp_flow_does_not_backtest_risk_rejected_strategy() -> None:
    def unsafe_generator(signal):
        manifest, code = generate_mock_strategy(signal)
        return manifest, code.replace("stoploss = -0.08", "# stoploss removed")

    result = run_mvp_flow(sample_signal(), strategy_generator=unsafe_generator)

    assert result.risk_audit.approved is False
    assert result.backtest is None
    assert result.workflow.state == WorkflowState.REVIEW_COMPLETED


def test_mvp_flow_reviews_failed_backtest() -> None:
    def failed_backtest(signal, manifest):
        return BacktestReport(
            backtest_id="backtest_failed",
            strategy_id=manifest.strategy_id,
            timerange="20240101-20260501",
            trades=0,
            win_rate=0,
            profit_factor=0,
            max_drawdown=0,
            total_return=0,
            status=BacktestStatus.FAILED,
            error="No trades were generated.",
        )

    result = run_mvp_flow(sample_signal(), backtest_runner=failed_backtest)

    assert result.backtest.status == BacktestStatus.FAILED
    assert result.review.failure_reason == "No trades were generated."
