from app.flows import run_human_led_research_flow
from app.models import ResearchThesis, ThesisStatus
from app.services.researcher import generate_thesis_strategy_candidates, rank_strategy_candidates
from app.storage import QuantRepository
from tests.test_models import sample_signal


def sample_thesis() -> ResearchThesis:
    return ResearchThesis(
        thesis_id="thesis_001",
        title="Volume Continuation After Absorption",
        status=ThesisStatus.READY_FOR_IMPLEMENTATION,
        market_observation="Large volume breakouts sometimes continue after shallow pullbacks.",
        hypothesis="If volume expansion appears with limited spread widening, continuation odds improve.",
        trade_logic="Enter only when a volume spike is confirmed by momentum and acceptable liquidity.",
        expected_regimes=["trending", "high_liquidity"],
        invalidation_conditions=["wide_spread", "failed_follow_through", "low_liquidity"],
        risk_notes=["Position sizing must be owned by portfolio risk controls."],
        linked_signal_ids=["signal_001"],
        constraints=["Long-only spot strategy; no leverage escalation."],
    )


def test_human_led_research_flow_persists_thesis_and_strategy(tmp_path) -> None:
    repository = QuantRepository()
    thesis = sample_thesis()
    signal = sample_signal()

    manifest, code = run_human_led_research_flow(
        thesis,
        signal,
        repository=repository,
        log_dir=tmp_path,
    )

    assert manifest.thesis_id == thesis.thesis_id
    assert thesis.hypothesis in manifest.assumptions
    assert repository.get_research_thesis(thesis.thesis_id) == thesis
    assert repository.get_strategy(manifest.strategy_id) == manifest
    assert "class" in code


def test_thesis_candidates_keep_human_thesis_traceability() -> None:
    thesis = sample_thesis()
    signal = sample_signal()

    candidates = generate_thesis_strategy_candidates(thesis, signal, count=2)
    result = rank_strategy_candidates(signal, candidates)

    assert len(candidates) == 2
    assert all(candidate.thesis_id == thesis.thesis_id for candidate in candidates)
    assert result.thesis_id == thesis.thesis_id
    assert result.selected_candidate_id is not None


def test_thesis_candidates_generate_distinct_template_code() -> None:
    thesis = sample_thesis()
    signal = sample_signal()

    candidates = generate_thesis_strategy_candidates(thesis, signal, count=3)
    codes = {candidate.strategy_code for candidate in candidates}

    assert len(codes) == 3
    assert "ema_fast" in candidates[1].strategy_code
    assert "range_high" in candidates[2].strategy_code


def test_thesis_candidates_apply_diagnosis_refinements() -> None:
    thesis = sample_thesis().model_copy(
        update={
            "constraints": [
                "Historical lesson: Add stricter setup quality filters before entry.",
                "Historical lesson: Redesign exits around asymmetric payoff.",
                "Historical lesson: Block continuation entries in ranging regimes.",
            ]
        }
    )
    signal = sample_signal()

    candidates = generate_thesis_strategy_candidates(thesis, signal, count=3)

    assert "stoploss = -0.04" in candidates[0].strategy_code
    assert 'dataframe["adx"] > 22' in candidates[0].strategy_code
    assert 'dataframe["volume"] > dataframe["volume_mean"] * 1.4' in candidates[0].strategy_code
    assert "Code was tightened using prior reviewer failure diagnoses." in candidates[0].ranking_reasons
    assert 'dataframe["adx"] > 25' in candidates[1].strategy_code
    assert 'dataframe["atr"] > dataframe["atr_mean"]' in candidates[2].strategy_code
