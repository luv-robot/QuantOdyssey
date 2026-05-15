from app.models import (
    AgentEvalCase,
    AgentEvalTarget,
    ResearchTaskStatus,
    ResearchTaskType,
    SupervisorFlagKind,
    SupervisorStatus,
)
from app.services.agent_eval import evaluate_agent_response, run_agent_eval_suite
from app.services.reviewer import build_review_session
from app.services.supervisor import build_supervisor_report, supervisor_chat_answer
from app.storage import QuantRepository
from tests.test_harness_budget_and_scratchpad import _task
from tests.test_review_session_v1 import (
    sample_backtest,
    sample_baseline,
    sample_design,
    sample_event,
    sample_pre_review,
    sample_review_case,
    sample_robustness,
)


def test_supervisor_report_flags_agent_eval_failure_and_budget_task() -> None:
    case = AgentEvalCase(
        case_id="case_fail",
        target_agent=AgentEvalTarget.REVIEWER,
        title="Reject baseline failure",
        prompt="Should reject baseline failure.",
        expected_terms=["baseline", "not ready"],
        prohibited_terms=["live candidate"],
    )
    result = evaluate_agent_response(case, "This is a live candidate.")
    eval_run = run_agent_eval_suite({"case_fail": "This is a live candidate."}, cases=[case])
    blocked_task = _task(
        task_id="task_blocked",
        task_type=ResearchTaskType.PARAMETER_SENSITIVITY_TEST,
        status=ResearchTaskStatus.BLOCKED,
        approval_required=True,
    )

    report = build_supervisor_report(agent_eval_run=eval_run, research_tasks=[blocked_task])

    assert result.passed is False
    assert report.status == SupervisorStatus.CRITICAL
    assert {flag.kind for flag in report.flags} >= {
        SupervisorFlagKind.AGENT_EVAL_FAILURE,
        SupervisorFlagKind.TASK_BUDGET_RISK,
    }


def test_supervisor_chat_routes_to_eval_and_review_context() -> None:
    eval_run = run_agent_eval_suite(
        {"case_fail": ""},
        cases=[
            AgentEvalCase(
                case_id="case_fail",
                target_agent=AgentEvalTarget.REVIEWER,
                title="Case",
                prompt="Prompt",
                expected_terms=["baseline"],
            )
        ],
    )
    review_session = _sample_review_session()
    report = build_supervisor_report(agent_eval_run=eval_run, review_sessions=[review_session])

    answer = supervisor_chat_answer(
        "最近 eval 有没有失败？",
        report=report,
        agent_eval_run=eval_run,
        review_sessions=[review_session],
    )

    assert "Agent Eval" in answer or "eval" in answer


def test_repository_persists_agent_eval_and_supervisor_report() -> None:
    repository = QuantRepository()
    eval_run = run_agent_eval_suite({})
    report = build_supervisor_report(agent_eval_run=eval_run)

    repository.save_agent_eval_run(eval_run)
    repository.save_supervisor_report(report)

    assert repository.get_agent_eval_run(eval_run.run_id) == eval_run
    assert repository.query_agent_eval_runs(limit=1) == [eval_run]
    assert repository.get_supervisor_report(report.report_id) == report
    assert repository.query_supervisor_reports(limit=1) == [report]


def _sample_review_session():
    return build_review_session(
        sample_pre_review(),
        sample_design(),
        sample_event(),
        sample_backtest(),
        sample_baseline(),
        sample_robustness(),
        sample_review_case(),
    )
