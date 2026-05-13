from app.models import BacktestReport, BacktestStatus
from app.services.backtester import validate_backtest_reliability
from app.storage import QuantRepository


def report(
    backtest_id: str,
    total_return: float = 0.2,
    status: BacktestStatus = BacktestStatus.PASSED,
    trades: int = 80,
) -> BacktestReport:
    return BacktestReport(
        backtest_id=backtest_id,
        strategy_id="strategy_001",
        timerange="20240101-20260501",
        trades=trades,
        win_rate=0.55,
        profit_factor=1.4 if status == BacktestStatus.PASSED else 0.8,
        sharpe=1.1 if status == BacktestStatus.PASSED else -0.2,
        max_drawdown=-0.08,
        total_return=total_return,
        status=status,
        error=None if status == BacktestStatus.PASSED else "Failed.",
    )


def test_backtest_validation_approves_stable_reports() -> None:
    validation = validate_backtest_reliability(
        report("main"),
        out_of_sample_report=report("oos", total_return=0.16),
        walk_forward_reports=[report("wf1", 0.12), report("wf2", 0.13)],
        sensitivity_reports=[report("sens1", 0.12), report("sens2", 0.11)],
        fee_slippage_report=report("fees", 0.1),
    )

    assert validation.approved is True
    assert validation.overfitting_detected is False
    assert validation.quality_passed is True
    assert validation.quality_score >= 65


def test_backtest_validation_rejects_overfit_report() -> None:
    validation = validate_backtest_reliability(
        report("main", total_return=0.5),
        out_of_sample_report=report("oos", total_return=0.05),
        walk_forward_reports=[report("wf1", 0.4)],
        sensitivity_reports=[report("sens1", 0.4)],
        fee_slippage_report=report("fees", 0.3),
    )

    assert validation.approved is False
    assert validation.overfitting_detected is True


def test_repository_persists_backtest_validation() -> None:
    repository = QuantRepository()
    validation = validate_backtest_reliability(
        report("main"),
        out_of_sample_report=report("oos", total_return=0.16),
        walk_forward_reports=[report("wf1", 0.12)],
        sensitivity_reports=[report("sens1", 0.12)],
        fee_slippage_report=report("fees", 0.1),
    )

    repository.save_backtest_validation(validation)

    assert repository.get_backtest_validation(validation.validation_id) == validation
