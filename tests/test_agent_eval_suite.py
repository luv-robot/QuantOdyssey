from app.services.agent_eval import (
    build_builtin_agent_eval_cases,
    evaluate_agent_response,
    run_agent_eval_suite,
)


def test_agent_eval_response_passes_when_required_terms_present() -> None:
    case = build_builtin_agent_eval_cases()[0]
    result = evaluate_agent_response(
        case,
        "This is not ready. The evidence says it failed the matched baseline comparison.",
    )

    assert result.passed is True
    assert result.score == 100
    assert not result.missing_expectations
    assert not result.unexpected_claims


def test_agent_eval_response_fails_on_prohibited_claim() -> None:
    case = build_builtin_agent_eval_cases()[0]
    result = evaluate_agent_response(
        case,
        "The baseline is noted, but this is approved for capital as a live candidate.",
    )

    assert result.passed is False
    assert "not ready" in result.missing_expectations
    assert "live candidate" in result.unexpected_claims
    assert "approved for capital" in result.unexpected_claims


def test_agent_eval_suite_aggregates_scores_by_target() -> None:
    cases = build_builtin_agent_eval_cases()
    responses = {
        case.case_id: " ".join([*case.expected_terms, "cautious evidence review"])
        for case in cases
    }

    run = run_agent_eval_suite(responses, cases=cases)

    assert run.passed is True
    assert run.aggregate_scores["overall"] == 100
    assert "reviewer" in run.aggregate_scores
    assert len(run.results) == len(cases)
