from app.models import (
    HarnessBudgetDecisionAction,
    HarnessBudgetPolicy,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
    ScratchpadEventType,
)
from app.services.harness import (
    append_scratchpad_event,
    apply_harness_budget_guardrails,
    create_scratchpad_run,
    read_scratchpad_events,
)


def test_scratchpad_appends_and_reads_jsonl_events(tmp_path) -> None:
    run = create_scratchpad_run(
        run_id="run/test 001",
        purpose="verify research trace",
        base_dir=tmp_path,
    )
    event = append_scratchpad_event(
        run_id=run.run_id,
        event_type=ScratchpadEventType.RESEARCH_TASK,
        payload={"task_id": "task_001", "status": "proposed"},
        base_dir=tmp_path,
        task_id="task_001",
        evidence_refs=["review_session:review_001"],
    )

    events = read_scratchpad_events(run_id=run.run_id, base_dir=tmp_path)

    assert run.scratchpad_path.endswith("run_test_001.jsonl")
    assert events == [event]
    assert events[0].payload["status"] == "proposed"


def test_harness_budget_marks_expensive_optimizer_task_for_approval() -> None:
    task = _task(
        task_id="task_optimizer",
        task_type=ResearchTaskType.PARAMETER_SENSITIVITY_TEST,
        estimated_cost=200,
        approval_required=False,
        autonomy_level=2,
    )

    guarded, decisions = apply_harness_budget_guardrails(
        [task],
        policy=HarnessBudgetPolicy(max_automatic_task_cost=50, max_optimizer_trials_per_strategy=100),
    )

    assert guarded[0].approval_required is True
    assert guarded[0].autonomy_level == 1
    assert guarded[0].status == ResearchTaskStatus.PROPOSED
    assert decisions[0].action == HarnessBudgetDecisionAction.REQUIRE_APPROVAL
    assert any("max_optimizer_trials_per_strategy" in reason for reason in decisions[0].reasons)


def test_harness_budget_blocks_repeated_terminal_failure_loop() -> None:
    task = _task(task_id="task_new", task_type=ResearchTaskType.BASELINE_TEST)
    existing = [
        _task(task_id=f"task_old_{index}", task_type=ResearchTaskType.BASELINE_TEST, status=ResearchTaskStatus.BLOCKED)
        for index in range(3)
    ]

    guarded, decisions = apply_harness_budget_guardrails(
        [task],
        existing_tasks=existing,
        policy=HarnessBudgetPolicy(max_repeated_failure_loops=3),
    )

    assert guarded[0].status == ResearchTaskStatus.BLOCKED
    assert guarded[0].approval_required is True
    assert decisions[0].action == HarnessBudgetDecisionAction.BLOCK


def _task(
    *,
    task_id: str,
    task_type: ResearchTaskType,
    estimated_cost: int = 10,
    approval_required: bool = False,
    autonomy_level: int = 2,
    status: ResearchTaskStatus = ResearchTaskStatus.PROPOSED,
) -> ResearchTask:
    return ResearchTask(
        task_id=task_id,
        task_type=task_type,
        subject_type="strategy_family",
        subject_id="funding_crowding_fade",
        hypothesis="Test a bounded research step.",
        rationale="Generated from review evidence.",
        required_experiments=["run bounded test"],
        success_metrics=["evidence improves"],
        failure_conditions=["evidence remains weak"],
        estimated_cost=estimated_cost,
        priority_score=70,
        approval_required=approval_required,
        autonomy_level=autonomy_level,
        status=status,
    )
