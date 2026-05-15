from __future__ import annotations

from uuid import uuid4

from app.models import (
    HarnessBudgetDecision,
    HarnessBudgetDecisionAction,
    HarnessBudgetPolicy,
    ResearchTask,
    ResearchTaskStatus,
    ResearchTaskType,
)


def apply_harness_budget_guardrails(
    tasks: list[ResearchTask],
    *,
    existing_tasks: list[ResearchTask] | None = None,
    policy: HarnessBudgetPolicy | None = None,
) -> tuple[list[ResearchTask], list[HarnessBudgetDecision]]:
    policy = policy or HarnessBudgetPolicy()
    existing_tasks = existing_tasks or []
    guarded_tasks: list[ResearchTask] = []
    decisions: list[HarnessBudgetDecision] = []

    for task in tasks:
        guarded, decision = _guard_task(task, existing_tasks=existing_tasks, policy=policy)
        guarded_tasks.append(guarded)
        decisions.append(decision)

    return guarded_tasks, decisions


def _guard_task(
    task: ResearchTask,
    *,
    existing_tasks: list[ResearchTask],
    policy: HarnessBudgetPolicy,
) -> tuple[ResearchTask, HarnessBudgetDecision]:
    reasons: list[str] = []
    action = HarnessBudgetDecisionAction.ALLOW
    status = task.status
    approval_required = task.approval_required
    autonomy_level = task.autonomy_level

    similar_terminal_failures = _similar_terminal_failure_count(task, existing_tasks)
    if similar_terminal_failures >= policy.max_repeated_failure_loops:
        action = HarnessBudgetDecisionAction.BLOCK
        status = ResearchTaskStatus.BLOCKED
        approval_required = True
        autonomy_level = min(autonomy_level, 1)
        reasons.append(
            f"similar terminal task count {similar_terminal_failures} reached "
            f"max_repeated_failure_loops={policy.max_repeated_failure_loops}"
        )

    if task.estimated_cost > policy.max_automatic_task_cost:
        if action != HarnessBudgetDecisionAction.BLOCK:
            action = HarnessBudgetDecisionAction.REQUIRE_APPROVAL
        approval_required = True
        autonomy_level = min(autonomy_level, 1)
        reasons.append(
            f"estimated_cost={task.estimated_cost} exceeds "
            f"max_automatic_task_cost={policy.max_automatic_task_cost}"
        )

    if (
        task.task_type == ResearchTaskType.PARAMETER_SENSITIVITY_TEST
        and task.estimated_cost > policy.max_optimizer_trials_per_strategy
    ):
        if action != HarnessBudgetDecisionAction.BLOCK:
            action = HarnessBudgetDecisionAction.REQUIRE_APPROVAL
        approval_required = True
        autonomy_level = min(autonomy_level, 1)
        reasons.append(
            f"parameter sensitivity cost {task.estimated_cost} exceeds "
            f"max_optimizer_trials_per_strategy={policy.max_optimizer_trials_per_strategy}"
        )

    if task.autonomy_level > policy.max_autonomy_level_without_approval and not approval_required:
        action = HarnessBudgetDecisionAction.REQUIRE_APPROVAL
        approval_required = True
        autonomy_level = policy.max_autonomy_level_without_approval
        reasons.append(
            f"autonomy_level={task.autonomy_level} exceeds "
            f"max_autonomy_level_without_approval={policy.max_autonomy_level_without_approval}"
        )

    if reasons:
        evidence_refs = [
            *task.evidence_refs,
            f"harness_budget:{action.value}",
        ]
        guarded = task.model_copy(
            update={
                "status": status,
                "approval_required": approval_required,
                "autonomy_level": autonomy_level,
                "evidence_refs": list(dict.fromkeys(evidence_refs)),
            }
        )
    else:
        guarded = task

    decision = HarnessBudgetDecision(
        decision_id=f"budget_{task.task_id}_{uuid4().hex[:8]}",
        task_id=task.task_id,
        action=action,
        reasons=reasons or ["within harness budget policy"],
        original_status=task.status,
        resulting_status=guarded.status,
        approval_required=guarded.approval_required,
    )
    return guarded, decision


def _similar_terminal_failure_count(task: ResearchTask, existing_tasks: list[ResearchTask]) -> int:
    terminal_statuses = {ResearchTaskStatus.BLOCKED, ResearchTaskStatus.REJECTED}
    return sum(
        1
        for existing in existing_tasks
        if existing.task_type == task.task_type
        and existing.subject_type == task.subject_type
        and existing.subject_id == task.subject_id
        and existing.status in terminal_statuses
    )
