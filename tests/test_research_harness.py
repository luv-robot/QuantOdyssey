from app.models import (
    BacktestStatus,
    BaselineComparisonReport,
    BaselineResult,
    DataSufficiencyLevel,
    ResearchTaskType,
    ReviewResult,
    RobustnessReport,
)
from app.services.harness import build_research_harness_cycle
from app.services.reviewer import build_review_session
from app.storage import QuantRepository
from tests.test_review_session_v1 import (
    sample_backtest,
    sample_baseline,
    sample_design,
    sample_event,
    sample_pre_review,
    sample_review_case,
    sample_robustness,
)


def test_harness_generates_findings_and_next_tasks_from_review_session() -> None:
    thesis = _sample_thesis()
    event = sample_event().model_copy(
        update={
            "validation_data_sufficiency_level": DataSufficiencyLevel.L1_FUNDING_OI,
            "missing_evidence": [],
            "features": {
                "event_count": 0,
                "trigger_count": 0,
                "funding_percentile_30d": 90,
                "open_interest_percentile_30d": 63.33,
                "failed_breakout_3bar": False,
            },
        }
    )
    session = build_review_session(
        sample_pre_review(),
        sample_design().model_copy(update={"validation_data_sufficiency_level": DataSufficiencyLevel.L1_FUNDING_OI}),
        event,
        sample_backtest().model_copy(
            update={
                "status": BacktestStatus.FAILED,
                "profit_factor": 0.48,
                "sharpe": -0.77,
                "total_return": -0.012,
                "error": "research criteria failed",
            }
        ),
        BaselineComparisonReport(
            report_id="baseline_harness",
            strategy_id="strategy_review_session",
            signal_id="signal_review_session",
            source_backtest_id="bt_review_session",
            strategy_total_return=-0.012,
            strategy_profit_factor=0.48,
            best_baseline_name="cash",
            best_baseline_return=0,
            outperformed_best_baseline=False,
            baselines=[
                BaselineResult(
                    name="cash",
                    description="No position.",
                    total_return=0,
                    profit_factor=0,
                    max_drawdown=0,
                    trades=0,
                )
            ],
        ),
        RobustnessReport(
            report_id="robustness_harness",
            strategy_id="strategy_review_session",
            source_backtest_id="bt_review_session",
            baseline_report_id="baseline_harness",
            monte_carlo_report_id="mc_harness",
            validation_id="validation_harness",
            statistical_confidence_score=33,
            robustness_score=32,
            passed=False,
            findings=["Robustness score is weak."],
        ),
        sample_review_case().model_copy(update={"result": ReviewResult.FAILED}),
    )

    cycle, findings, tasks = build_research_harness_cycle(
        thesis=thesis,
        event_episode=event,
        review_sessions=[session],
    )
    task_types = {task.task_type for task in tasks}

    assert cycle.finding_ids == [findings[0].finding_id]
    assert ResearchTaskType.EVENT_DEFINITION_TEST in task_types
    assert ResearchTaskType.PARAMETER_SENSITIVITY_TEST in task_types
    assert ResearchTaskType.EVENT_FREQUENCY_SCAN in task_types
    assert any(task.approval_required for task in tasks if task.task_type == ResearchTaskType.PARAMETER_SENSITIVITY_TEST)
    assert any("event_count=0" in item for item in findings[0].observations)


def test_repository_persists_harness_artifacts() -> None:
    repository = QuantRepository()
    thesis = _sample_thesis()
    event = sample_event()
    session = build_review_session(
        sample_pre_review(),
        sample_design(),
        event,
        sample_backtest(),
        sample_baseline(),
        sample_robustness(),
        sample_review_case(),
    )
    cycle, findings, tasks = build_research_harness_cycle(
        thesis=thesis,
        event_episode=event,
        review_sessions=[session],
    )

    repository.save_research_finding(findings[0])
    repository.save_research_task(tasks[0])
    repository.save_research_harness_cycle(cycle)

    assert repository.get_research_finding(findings[0].finding_id) == findings[0]
    assert repository.query_research_findings(signal_id=event.signal_id)
    assert repository.get_research_task(tasks[0].task_id) == tasks[0]
    assert repository.query_research_tasks(thesis_id=thesis.thesis_id)
    assert repository.get_research_harness_cycle(cycle.cycle_id) == cycle
    assert repository.query_research_harness_cycles(signal_id=event.signal_id) == [cycle]


def _sample_thesis():
    from app.models import ResearchThesis

    return ResearchThesis(
        thesis_id="thesis_review_session",
        title="Funding Crowding Fade",
        market_observation="Positive funding can mark crowded longs.",
        hypothesis="Crowded longs fade after funding, OI, and failed breakout align.",
        trade_logic="Short after failed upside extension.",
        expected_regimes=["event-driven funding crowding"],
        invalidation_conditions=["price accepts above breakout high"],
    )
