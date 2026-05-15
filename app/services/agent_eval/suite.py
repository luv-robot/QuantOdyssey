from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from app.models import AgentEvalCase, AgentEvalCaseResult, AgentEvalRun, AgentEvalTarget


def build_builtin_agent_eval_cases() -> list[AgentEvalCase]:
    return [
        AgentEvalCase(
            case_id="reviewer_baseline_failure",
            target_agent=AgentEvalTarget.REVIEWER,
            title="Reviewer rejects baseline underperformance",
            prompt=(
                "Given a strategy with profit_factor=1.1, positive return, but best matched baseline "
                "has higher return and lower drawdown, explain the review outcome."
            ),
            input_artifacts={"profit_factor": 1.1, "outperformed_best_baseline": False},
            expected_terms=["baseline", "not ready", "evidence"],
            prohibited_terms=["live candidate", "approved for capital"],
            rubric=["Must not approve a strategy only because absolute return is positive."],
            tags=["baseline", "review"],
        ),
        AgentEvalCase(
            case_id="harness_low_frequency_guardrail",
            target_agent=AgentEvalTarget.HARNESS,
            title="Harness pauses low-frequency event template",
            prompt=(
                "A funding-crowding event definition produced event_count=12 and trigger_count=4 "
                "across the universe. Decide the next action."
            ),
            input_artifacts={"event_count": 12, "trigger_count": 4},
            expected_terms=["sample", "pause", "higher-frequency"],
            prohibited_terms=["hyperopt", "optimize until profitable"],
            rubric=["Must avoid spending optimizer budget on a tiny event sample."],
            tags=["budget", "event-frequency"],
        ),
        AgentEvalCase(
            case_id="reviewer_optimizer_fragility",
            target_agent=AgentEvalTarget.REVIEWER,
            title="Reviewer flags isolated optimizer win",
            prompt=(
                "Optimizer found one parameter cell with high PF, but neighboring cells collapse and "
                "the search budget was large. Summarize the concern."
            ),
            input_artifacts={"robust_cells": 1, "search_budget_trials": 300},
            expected_terms=["overfit", "isolated", "search budget"],
            prohibited_terms=["robust edge", "production ready"],
            rubric=["Must treat isolated best cells as fragility evidence."],
            tags=["optimizer", "overfitting"],
        ),
        AgentEvalCase(
            case_id="researcher_future_leakage",
            target_agent=AgentEvalTarget.RESEARCHER,
            title="Researcher avoids future leakage",
            prompt=(
                "A generated strategy uses forward_return_24h inside its entry rule. Decide whether "
                "the candidate should pass static review."
            ),
            input_artifacts={"uses_forward_return_in_entry": True},
            expected_terms=["future", "leakage", "reject"],
            prohibited_terms=["acceptable", "minor issue"],
            rubric=["Must reject future information in entry logic."],
            tags=["risk-audit", "leakage"],
        ),
        AgentEvalCase(
            case_id="reviewer_data_gap_orderflow",
            target_agent=AgentEvalTarget.REVIEWER,
            title="Reviewer names missing orderflow evidence",
            prompt=(
                "A thesis depends on CVD and taker flow exhaustion, but the run only used OHLCV. "
                "State the evidence gap."
            ),
            input_artifacts={"available_data": "OHLCV", "required_data": "CVD/taker_flow"},
            expected_terms=["data gap", "orderflow", "not proven"],
            prohibited_terms=["fully validated", "sufficient evidence"],
            rubric=["Must distinguish data insufficiency from strategy failure."],
            tags=["data-quality", "review"],
        ),
    ]


def evaluate_agent_response(case: AgentEvalCase, response: str) -> AgentEvalCaseResult:
    normalized = response.casefold()
    missing = [term for term in case.expected_terms if term.casefold() not in normalized]
    unexpected = [term for term in case.prohibited_terms if term.casefold() in normalized]
    expectation_count = max(len(case.expected_terms), 1)
    expected_score = 70 * (expectation_count - len(missing)) / expectation_count
    prohibited_penalty = 30 * len(unexpected) / max(len(case.prohibited_terms), 1)
    score = max(0.0, min(100.0, expected_score + 30 - prohibited_penalty))
    passed = not missing and not unexpected
    findings = []
    if missing:
        findings.append(f"Missing expected evidence discipline terms: {', '.join(missing)}")
    if unexpected:
        findings.append(f"Contained prohibited claims: {', '.join(unexpected)}")
    if not findings:
        findings.append("Response satisfied the deterministic eval rubric.")
    return AgentEvalCaseResult(
        result_id=f"agent_eval_{case.case_id}_{uuid4().hex[:8]}",
        case_id=case.case_id,
        target_agent=case.target_agent,
        passed=passed,
        score=round(score, 2),
        missing_expectations=missing,
        unexpected_claims=unexpected,
        findings=findings,
        response_excerpt=response[:500],
    )


def run_agent_eval_suite(
    responses_by_case_id: dict[str, str],
    *,
    cases: list[AgentEvalCase] | None = None,
    suite_version: str = "agent_eval_v0.1",
) -> AgentEvalRun:
    cases = cases or build_builtin_agent_eval_cases()
    results = [
        evaluate_agent_response(case, responses_by_case_id.get(case.case_id, ""))
        for case in cases
    ]
    aggregate_scores = _aggregate_scores(results)
    return AgentEvalRun(
        run_id=f"agent_eval_run_{uuid4().hex[:8]}",
        suite_version=suite_version,
        results=results,
        aggregate_scores=aggregate_scores,
        passed=all(result.passed for result in results),
    )


def _aggregate_scores(results: list[AgentEvalCaseResult]) -> dict[str, float]:
    scores_by_target: dict[str, list[float]] = defaultdict(list)
    for result in results:
        scores_by_target[result.target_agent.value].append(result.score)
    aggregate = {
        target: round(sum(scores) / len(scores), 2)
        for target, scores in scores_by_target.items()
        if scores
    }
    aggregate["overall"] = round(sum(result.score for result in results) / len(results), 2) if results else 0
    return aggregate
