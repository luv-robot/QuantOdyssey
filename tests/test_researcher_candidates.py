from app.services.researcher import (
    INDICATOR_WHITELIST,
    generate_strategy_candidates,
    rank_strategy_candidates,
)
from tests.test_models import sample_signal


def test_generate_strategy_candidates_uses_template_library_and_whitelist() -> None:
    candidates = generate_strategy_candidates(sample_signal(), count=3)

    assert len(candidates) == 3
    assert all(set(candidate.indicators).issubset(INDICATOR_WHITELIST) for candidate in candidates)
    assert all(candidate.manifest.assumptions for candidate in candidates)


def test_rank_strategy_candidates_selects_highest_scoring_candidate() -> None:
    signal = sample_signal(rank_score=82)
    candidates = generate_strategy_candidates(signal, count=3)

    result = rank_strategy_candidates(signal, candidates)

    assert result.selected_candidate_id == result.candidates[0].candidate_id
    assert result.candidates[0].score >= result.candidates[-1].score


def test_rank_strategy_candidates_penalizes_duplicate_code() -> None:
    signal = sample_signal(rank_score=82)
    candidates = generate_strategy_candidates(signal, count=1)

    result = rank_strategy_candidates(signal, candidates, existing_strategy_code=candidates[0].strategy_code)

    assert result.candidates[0].score < candidates[0].score
    assert "similar" in result.candidates[0].ranking_reasons[-1]
