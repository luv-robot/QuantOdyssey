from __future__ import annotations

from app.models import CandidateRankingResult, MarketSignal, ResearchThesis, StrategyCandidate
from app.services.researcher.mock_researcher import (
    build_strategy_code,
    generate_mock_strategy,
    generate_strategy_from_thesis,
)
from app.services.strategy_registry import detect_duplicate_strategy


INDICATOR_WHITELIST = {
    "rsi",
    "volume_mean",
    "ema",
    "adx",
    "atr",
    "funding_rate",
    "funding_percentile",
    "open_interest",
    "open_interest_percentile",
    "failed_breakout",
}
TEMPLATE_LIBRARY = {
    "funding_crowding_fade_short": [
        "funding_rate",
        "funding_percentile",
        "open_interest",
        "open_interest_percentile",
        "failed_breakout",
        "atr",
    ],
    "volume_momentum": ["rsi", "volume_mean"],
    "trend_confirmation": ["ema", "adx", "volume_mean"],
    "volatility_breakout": ["atr", "volume_mean", "rsi"],
}


def generate_strategy_candidates(signal: MarketSignal, count: int = 3) -> list[StrategyCandidate]:
    candidates: list[StrategyCandidate] = []
    templates = _generic_templates(count)
    for index, (template_name, indicators) in enumerate(templates, start=1):
        manifest, _ = generate_mock_strategy(signal)
        manifest = manifest.model_copy(
            update={
                "strategy_id": f"{manifest.strategy_id}_candidate_{index}",
                "name": f"{manifest.name}Candidate{index}",
                "file_path": manifest.file_path.replace(".py", f"Candidate{index}.py"),
            }
        )
        code = build_strategy_code(manifest.name, manifest.timeframe, template_name=template_name)
        candidates.append(
            StrategyCandidate(
                candidate_id=f"candidate_{manifest.strategy_id}",
                manifest=manifest,
                strategy_code=code,
                score=_score_candidate(signal, indicators),
                ranking_reasons=[
                    f"Template {template_name} uses whitelisted indicators.",
                    "Candidate includes stoploss and explicit exits.",
                ],
                template_name=template_name,
                indicators=indicators,
            )
        )
    return candidates


def generate_thesis_strategy_candidates(
    thesis: ResearchThesis,
    signal: MarketSignal,
    count: int = 3,
) -> list[StrategyCandidate]:
    candidates: list[StrategyCandidate] = []
    templates = _templates_for_thesis(thesis, count)
    refinement_profile = _refinement_profile_from_thesis(thesis)
    for index, (template_name, indicators) in enumerate(templates, start=1):
        manifest, _ = generate_strategy_from_thesis(thesis, signal)
        manifest = manifest.model_copy(
            update={
                "strategy_id": f"{manifest.strategy_id}_candidate_{index}",
                "name": f"{manifest.name}Candidate{index}",
                "file_path": manifest.file_path.replace(".py", f"Candidate{index}.py"),
            }
        )
        code = build_strategy_code(
            manifest.name,
            manifest.timeframe,
            template_name=template_name,
            refinement_profile=refinement_profile,
        )
        ranking_reasons = [
            f"Implements human thesis {thesis.thesis_id} using template {template_name}.",
            "Candidate includes explicit assumptions and invalidation conditions.",
            "Agent contribution is implementation scaffolding, not alpha discovery.",
        ]
        if refinement_profile is not None:
            ranking_reasons.append(
                "Code was tightened using prior reviewer failure diagnoses."
            )
        candidates.append(
            StrategyCandidate(
                candidate_id=f"candidate_{manifest.strategy_id}",
                thesis_id=thesis.thesis_id,
                manifest=manifest,
                strategy_code=code,
                score=_score_thesis_candidate(thesis, signal, indicators),
                ranking_reasons=ranking_reasons,
                template_name=template_name,
                indicators=indicators,
            )
        )
    return candidates


def rank_strategy_candidates(
    signal: MarketSignal,
    candidates: list[StrategyCandidate],
    existing_strategy_code: str | None = None,
    duplicate_threshold: float = 0.9,
) -> CandidateRankingResult:
    ranked = []
    for candidate in candidates:
        if not set(candidate.indicators).issubset(INDICATOR_WHITELIST):
            continue
        if existing_strategy_code is not None:
            similarity = detect_duplicate_strategy(
                candidate.manifest.strategy_id,
                candidate.strategy_code,
                "existing_strategy",
                existing_strategy_code,
                threshold=duplicate_threshold,
            )
            if similarity.is_duplicate:
                candidate = candidate.model_copy(
                    update={
                        "score": max(0, candidate.score - 50),
                        "ranking_reasons": candidate.ranking_reasons
                        + ["Penalized because candidate is similar to an existing strategy."],
                    }
                )
        ranked.append(candidate)

    ranked = sorted(ranked, key=lambda item: item.score, reverse=True)
    return CandidateRankingResult(
        signal_id=signal.signal_id,
        thesis_id=candidates[0].thesis_id if candidates else None,
        candidates=ranked,
        selected_candidate_id=ranked[0].candidate_id if ranked else None,
    )


def _score_candidate(signal: MarketSignal, indicators: list[str]) -> float:
    score = signal.rank_score * 0.7 + len(indicators) * 5
    if "volume_mean" in indicators and signal.signal_type.value == "volume_spike":
        score += 10
    return min(100, round(score, 2))


def _score_thesis_candidate(
    thesis: ResearchThesis,
    signal: MarketSignal,
    indicators: list[str],
) -> float:
    score = _score_candidate(signal, indicators)
    if thesis.linked_signal_ids and signal.signal_id in thesis.linked_signal_ids:
        score += 10
    if thesis.invalidation_conditions:
        score += 5
    if thesis.expected_regimes:
        score += 5
    if _refinement_profile_from_thesis(thesis) is not None:
        score += 3
    if any(term in " ".join([thesis.title, thesis.hypothesis, thesis.trade_logic]).lower() for term in ["funding", "资金费率"]):
        score += 6
    return min(100, round(score, 2))


def _generic_templates(count: int) -> list[tuple[str, list[str]]]:
    names = ["volume_momentum", "trend_confirmation", "volatility_breakout"]
    return [(name, TEMPLATE_LIBRARY[name]) for name in names[:count]]


def _templates_for_thesis(thesis: ResearchThesis, count: int) -> list[tuple[str, list[str]]]:
    text = " ".join([thesis.title, thesis.market_observation, thesis.hypothesis, thesis.trade_logic]).lower()
    if any(term in text for term in ["funding", "资金费率"]):
        preferred = [
            ("funding_crowding_fade_short", TEMPLATE_LIBRARY["funding_crowding_fade_short"]),
            ("volatility_breakout", TEMPLATE_LIBRARY["volatility_breakout"]),
            ("trend_confirmation", TEMPLATE_LIBRARY["trend_confirmation"]),
            ("volume_momentum", TEMPLATE_LIBRARY["volume_momentum"]),
        ]
        return preferred[:count]
    return _generic_templates(count)


def _refinement_profile_from_thesis(thesis: ResearchThesis) -> str | None:
    context = " ".join([*thesis.constraints, *thesis.invalidation_conditions]).lower()
    diagnosis_markers = [
        "entry_too_broad",
        "payoff_profile_weak",
        "regime_mismatch",
        "monte_carlo_unstable",
        "stricter setup quality",
        "redesign exits",
        "block continuation",
        "do not promote",
        "recalibrate signal rank",
    ]
    if any(marker in context for marker in diagnosis_markers):
        return "diagnosis_refined"
    return None
