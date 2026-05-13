from app.flows import run_backtest_flow, run_research_flow, run_review_flow, run_risk_audit_flow
from app.models import ReviewResult
from app.services.risk_auditor import audit_strategy_code
from app.storage import InMemoryReviewStore, QuantRepository
from tests.test_models import sample_signal


def test_stage_flows_can_run_independently(tmp_path) -> None:
    repository = QuantRepository()
    signal = sample_signal()

    manifest, code = run_research_flow(signal, repository=repository, log_dir=tmp_path / "logs")
    risk = run_risk_audit_flow(code, manifest, repository=repository)
    backtest = run_backtest_flow(signal, manifest, risk, repository=repository)
    review = run_review_flow(
        signal,
        manifest,
        risk,
        backtest,
        review_store=InMemoryReviewStore(),
        repository=repository,
    )

    assert repository.get_strategy(manifest.strategy_id) == manifest
    assert repository.get_risk_audit(manifest.strategy_id) == risk
    assert repository.get_backtest(backtest.backtest_id) == backtest
    assert repository.get_review(review.case_id) == review
    assert (tmp_path / "logs" / f"{manifest.strategy_id}.prompt.json").exists()
    assert (tmp_path / "logs" / f"{manifest.strategy_id}.response.json").exists()


def test_backtest_flow_skips_rejected_strategy() -> None:
    signal = sample_signal()
    manifest, code = run_research_flow(signal)
    unsafe_code = code.replace("stoploss = -0.08", "# stoploss removed")
    risk = audit_strategy_code(unsafe_code, manifest)

    assert run_backtest_flow(signal, manifest, risk) is None


def test_review_flow_handles_risk_rejection() -> None:
    signal = sample_signal()
    manifest, code = run_research_flow(signal)
    risk = audit_strategy_code(code.replace("stoploss = -0.08", "# stoploss removed"), manifest)

    review = run_review_flow(signal, manifest, risk)

    assert review.result == ReviewResult.RISK_REJECTED
    assert review.failure_reason
