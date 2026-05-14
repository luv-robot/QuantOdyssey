from __future__ import annotations

from app.models import (
    BacktestReport,
    BaselineComparisonReport,
    EventEpisode,
    ResearchDesignDraft,
    ResearchMaturityScore,
    ReviewCase,
    ReviewClaim,
    ReviewQuestion,
    ReviewSession,
    RobustnessReport,
    ThesisPreReview,
)


def build_review_session(
    pre_review: ThesisPreReview,
    research_design: ResearchDesignDraft,
    event_episode: EventEpisode,
    backtest: BacktestReport,
    baseline: BaselineComparisonReport,
    robustness: RobustnessReport,
    review_case: ReviewCase | None = None,
) -> ReviewSession:
    maturity = _build_maturity_score(pre_review, research_design, backtest, baseline, robustness)
    return ReviewSession(
        session_id=f"review_session_{backtest.backtest_id}",
        thesis_id=research_design.thesis_id,
        signal_id=event_episode.signal_id,
        strategy_id=backtest.strategy_id,
        review_case_id=None if review_case is None else review_case.case_id,
        scorecard={
            "profit_factor": backtest.profit_factor,
            "sharpe": backtest.sharpe,
            "max_drawdown": backtest.max_drawdown,
            "total_return": backtest.total_return,
            "trades": backtest.trades,
            "best_baseline": baseline.best_baseline_name,
            "outperformed_best_baseline": baseline.outperformed_best_baseline,
            "robustness_score": robustness.robustness_score,
            "statistical_confidence_score": robustness.statistical_confidence_score,
            "validation_data_sufficiency_level": research_design.validation_data_sufficiency_level.value,
        },
        evidence_for=_evidence_for(backtest, baseline, robustness, review_case),
        evidence_against=_evidence_against(backtest, baseline, robustness),
        blind_spots=_blind_spots(research_design, event_episode, baseline),
        ai_questions=_ai_questions(pre_review, research_design),
        next_experiments=_next_experiments(research_design, baseline, robustness),
        user_responses=[],
        maturity_score=maturity,
    )


def _build_maturity_score(
    pre_review: ThesisPreReview,
    research_design: ResearchDesignDraft,
    backtest: BacktestReport,
    baseline: BaselineComparisonReport,
    robustness: RobustnessReport,
) -> ResearchMaturityScore:
    thesis_clarity = round((pre_review.completeness_score + pre_review.condition_clarity_score) / 2, 2)
    data_sufficiency = 80 if research_design.validation_data_sufficiency_level == research_design.data_sufficiency_level else 55
    sample_maturity = min(100, round(backtest.trades / 80 * 100, 2))
    baseline_advantage = 85 if baseline.outperformed_best_baseline else 35
    robustness_score = robustness.robustness_score
    regime_stability = 45
    failure_understanding = 70 if review_case_like_findings(robustness.findings) else 45
    implementation_safety = 80
    overfit_risk = max(0, 100 - robustness.statistical_confidence_score)
    components = [
        thesis_clarity,
        data_sufficiency,
        sample_maturity,
        baseline_advantage,
        robustness_score,
        regime_stability,
        failure_understanding,
        implementation_safety,
        100 - overfit_risk,
    ]
    overall = round(sum(components) / len(components), 2)
    blockers = []
    if research_design.missing_evidence:
        blockers.append("Missing future evidence: " + ", ".join(research_design.missing_evidence) + ".")
    if not baseline.outperformed_best_baseline:
        blockers.append("Strategy has not outperformed the best matched baseline.")
    if backtest.trades < 80:
        blockers.append("Trade sample is below the current maturity threshold.")
    if robustness.robustness_score < 70:
        blockers.append("Robustness score is below the current research threshold.")
    return ResearchMaturityScore(
        overall_score=overall,
        thesis_clarity=thesis_clarity,
        data_sufficiency=data_sufficiency,
        sample_maturity=sample_maturity,
        baseline_advantage=baseline_advantage,
        robustness=robustness_score,
        regime_stability=regime_stability,
        failure_understanding=failure_understanding,
        implementation_safety=implementation_safety,
        overfit_risk=round(overfit_risk, 2),
        stage=_stage(overall, blockers),
        blockers=blockers,
    )


def review_case_like_findings(findings: list[str]) -> bool:
    return bool(findings)


def _evidence_for(
    backtest: BacktestReport,
    baseline: BaselineComparisonReport,
    robustness: RobustnessReport,
    review_case: ReviewCase | None,
) -> list[ReviewClaim]:
    claims = []
    if backtest.profit_factor >= 1.2:
        claims.append(
            ReviewClaim(
                claim_id="evidence_for_profit_factor",
                claim_type="performance",
                statement=f"Profit factor is {backtest.profit_factor:.2f}, above the first-pass threshold.",
                evidence_refs=[f"backtest:{backtest.backtest_id}:profit_factor"],
            )
        )
    if baseline.outperformed_best_baseline:
        claims.append(
            ReviewClaim(
                claim_id="evidence_for_baseline",
                claim_type="baseline",
                statement=f"Strategy outperformed the best matched baseline: {baseline.best_baseline_name}.",
                evidence_refs=[f"baseline:{baseline.report_id}:best_baseline_name"],
            )
        )
    if robustness.passed:
        claims.append(
            ReviewClaim(
                claim_id="evidence_for_robustness",
                claim_type="robustness",
                statement=f"Robustness score is {robustness.robustness_score:.2f}.",
                evidence_refs=[f"robustness:{robustness.report_id}:robustness_score"],
            )
        )
    if review_case is not None and review_case.reusable_lessons:
        claims.append(
            ReviewClaim(
                claim_id="evidence_for_review_lessons",
                claim_type="review",
                statement="Review case produced reusable lessons for future research.",
                evidence_refs=[f"review:{review_case.case_id}:reusable_lessons"],
            )
        )
    return claims


def _evidence_against(
    backtest: BacktestReport,
    baseline: BaselineComparisonReport,
    robustness: RobustnessReport,
) -> list[ReviewClaim]:
    claims = []
    if backtest.trades < 80:
        claims.append(
            ReviewClaim(
                claim_id="evidence_against_sample",
                claim_type="sample_maturity",
                statement=f"Trade count is {backtest.trades}, below the 80-trade maturity reference.",
                evidence_refs=[f"backtest:{backtest.backtest_id}:trades"],
                severity="high",
            )
        )
    if not baseline.outperformed_best_baseline:
        claims.append(
            ReviewClaim(
                claim_id="evidence_against_baseline",
                claim_type="baseline",
                statement="Strategy did not outperform the best matched baseline.",
                evidence_refs=[f"baseline:{baseline.report_id}:outperformed_best_baseline"],
                severity="high",
            )
        )
    if not robustness.passed:
        claims.append(
            ReviewClaim(
                claim_id="evidence_against_robustness",
                claim_type="robustness",
                statement="Robustness checks did not pass.",
                evidence_refs=[f"robustness:{robustness.report_id}:passed"],
                severity="high",
            )
        )
    return claims


def _blind_spots(
    research_design: ResearchDesignDraft,
    event_episode: EventEpisode,
    baseline: BaselineComparisonReport,
) -> list[ReviewClaim]:
    claims = []
    if research_design.missing_evidence:
        claims.append(
            ReviewClaim(
                claim_id="blind_spot_missing_evidence",
                claim_type="data_sufficiency",
                statement="Current validation does not include all evidence required by the full thesis.",
                evidence_refs=[
                    f"design:{research_design.design_id}:missing_evidence",
                    f"event:{event_episode.event_id}:missing_evidence",
                ],
                severity="high",
            )
        )
    if any("proxy" in item.name for item in baseline.baselines):
        claims.append(
            ReviewClaim(
                claim_id="blind_spot_proxy_baselines",
                claim_type="baseline",
                statement="Baseline comparison still uses proxy baselines and should be replaced by event-level backtests.",
                evidence_refs=[f"baseline:{baseline.report_id}:baselines"],
                severity="medium",
            )
        )
    return claims


def _ai_questions(
    pre_review: ThesisPreReview,
    research_design: ResearchDesignDraft,
) -> list[ReviewQuestion]:
    questions = [
        ReviewQuestion(
            question_id=f"pre_review_question_{index}",
            question=item,
            why_it_matters="This was unresolved before strategy implementation and should be revisited after results.",
            evidence_refs=[f"pre_review:{pre_review.pre_review_id}:unresolved_questions"],
        )
        for index, item in enumerate(pre_review.unresolved_questions, start=1)
    ]
    if research_design.missing_evidence:
        questions.append(
            ReviewQuestion(
                question_id="question_missing_evidence_priority",
                question="Which missing evidence should be added first to reduce mechanism uncertainty?",
                why_it_matters="The thesis may require data that the current validation did not include.",
                evidence_refs=[f"design:{research_design.design_id}:missing_evidence"],
            )
        )
    return questions


def _next_experiments(
    research_design: ResearchDesignDraft,
    baseline: BaselineComparisonReport,
    robustness: RobustnessReport,
) -> list[str]:
    experiments = []
    if any("proxy" in item.name for item in baseline.baselines):
        experiments.append("Replace proxy baselines with event-level baseline backtests.")
    if research_design.missing_evidence:
        experiments.append("Run a data sufficiency upgrade experiment for: " + ", ".join(research_design.missing_evidence) + ".")
    if robustness.robustness_score < 80:
        experiments.append("Run parameter sensitivity and walk-forward checks around the selected setup.")
    experiments.append("Bucket performance by market regime and compare failure modes.")
    return experiments


def _stage(overall: float, blockers: list[str]) -> str:
    if blockers and overall < 70:
        return "promising_but_immature"
    if overall >= 80 and not blockers:
        return "robust_enough_for_deeper_test"
    if overall >= 60:
        return "structured_evidence"
    return "weak_or_incomplete_evidence"
