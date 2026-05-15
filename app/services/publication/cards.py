from __future__ import annotations

from datetime import datetime

from app.models import (
    ArenaScoreReport,
    BacktestReport,
    BaselineComparisonReport,
    EvaluationType,
    PublicArtifactStatus,
    PublicArtifactVisibility,
    PublicStrategyCard,
    PublicThesisCard,
    ResearchDesignDraft,
    ResearchThesis,
    ReviewSession,
    StrategyFamily,
    StrategyManifest,
)


PRIVATE_STRATEGY_REDACTIONS = [
    "strategy_code",
    "strategy_file_path",
    "exact_parameters",
    "complete_trade_log",
    "private_prompt",
    "private_ai_review_commentary",
]


def build_public_thesis_card(
    thesis: ResearchThesis,
    *,
    design: ResearchDesignDraft | None = None,
    review_session: ReviewSession | None = None,
    baseline: BaselineComparisonReport | None = None,
    arena_score: ArenaScoreReport | None = None,
    visibility: PublicArtifactVisibility = PublicArtifactVisibility.PRIVATE,
    status: PublicArtifactStatus = PublicArtifactStatus.DRAFT,
) -> PublicThesisCard:
    strategy_family = StrategyFamily.GENERAL_OR_UNKNOWN if design is None else design.inferred_strategy_family
    evaluation_type = None if design is None else design.evaluation_type
    public_metrics = {}
    if arena_score is not None:
        public_metrics.update(
            {
                "arena_score": arena_score.final_score,
                "arena_scoring_version": arena_score.scoring_version,
            }
        )
    if baseline is not None:
        public_metrics.update(
            {
                "outperformed_best_baseline": baseline.outperformed_best_baseline,
                "best_baseline_name": baseline.best_baseline_name,
                "best_baseline_return": baseline.best_baseline_return,
            }
        )
    if review_session is not None:
        public_metrics["research_maturity_score"] = review_session.maturity_score.overall_score

    return PublicThesisCard(
        public_id=f"public_thesis_{thesis.thesis_id}",
        thesis_id=thesis.thesis_id,
        title=thesis.title,
        strategy_family=strategy_family,
        evaluation_type=evaluation_type,
        visibility=visibility,
        status=status,
        public_summary=_clip(f"{thesis.market_observation} {thesis.hypothesis}", 420),
        market_observation_summary=_clip(thesis.market_observation, 360),
        hypothesis_summary=_clip(thesis.hypothesis, 360),
        data_requirements=[] if design is None else design.required_data,
        baseline_summary=_baseline_summary(baseline),
        regime_notes=list(thesis.expected_regimes),
        ai_review_summary=_review_summary(review_session),
        next_experiments=[] if review_session is None else review_session.next_experiments[:5],
        public_metrics=public_metrics,
        redacted_fields=[
            "full_trade_logic",
            "private_constraints",
            "complete_review_session",
            "prompt_logs",
            "model_responses",
        ],
        evidence_refs=_evidence_refs(thesis, design, review_session, baseline, arena_score),
    )


def build_public_strategy_card(
    strategy: StrategyManifest,
    *,
    backtest: BacktestReport | None = None,
    baseline: BaselineComparisonReport | None = None,
    review_session: ReviewSession | None = None,
    arena_score: ArenaScoreReport | None = None,
    strategy_family: StrategyFamily = StrategyFamily.GENERAL_OR_UNKNOWN,
    visibility: PublicArtifactVisibility = PublicArtifactVisibility.PRIVATE,
    status: PublicArtifactStatus = PublicArtifactStatus.DRAFT,
) -> PublicStrategyCard:
    public_metrics = {}
    if backtest is not None:
        public_metrics.update(
            {
                "timerange": backtest.timerange,
                "total_return": backtest.total_return,
                "profit_factor": backtest.profit_factor,
                "sharpe": backtest.sharpe,
                "max_drawdown": backtest.max_drawdown,
                "trades": backtest.trades,
                "status": backtest.status.value,
            }
        )
    if baseline is not None:
        public_metrics.update(
            {
                "best_baseline_name": baseline.best_baseline_name,
                "best_baseline_return": baseline.best_baseline_return,
                "outperformed_best_baseline": baseline.outperformed_best_baseline,
            }
        )
    if arena_score is not None:
        public_metrics.update(
            {
                "arena_score": arena_score.final_score,
                "overfit_penalty": arena_score.overfit_penalty,
            }
        )

    labels = [] if arena_score is None else arena_score.labels
    if review_session is not None and review_session.maturity_score.blockers:
        labels = [*labels, "review_blockers_present"]

    return PublicStrategyCard(
        public_id=f"public_strategy_{strategy.strategy_id}",
        strategy_id=strategy.strategy_id,
        thesis_id=strategy.thesis_id,
        title=strategy.name,
        strategy_family=strategy_family,
        visibility=visibility,
        status=status,
        public_description=_strategy_description(strategy),
        evaluation_summary=_strategy_evaluation_summary(backtest, baseline, review_session, arena_score),
        public_metrics=public_metrics,
        labels=list(dict.fromkeys(labels)),
        benchmark_refs=[] if baseline is None else [f"baseline_comparison:{baseline.report_id}"],
        redacted_fields=PRIVATE_STRATEGY_REDACTIONS,
        evidence_refs=_evidence_refs(strategy, backtest, baseline, review_session, arena_score),
    )


def _baseline_summary(baseline: BaselineComparisonReport | None) -> str | None:
    if baseline is None:
        return None
    status = "outperformed" if baseline.outperformed_best_baseline else "did not outperform"
    return (
        f"Strategy {status} best baseline `{baseline.best_baseline_name}` "
        f"over the matched evaluation set."
    )


def _review_summary(session: ReviewSession | None) -> str | None:
    if session is None:
        return None
    blockers = "; ".join(session.maturity_score.blockers[:2])
    if blockers:
        return f"Research maturity {session.maturity_score.overall_score:.1f}; blockers: {blockers}."
    return f"Research maturity {session.maturity_score.overall_score:.1f}; no major public-score blockers recorded."


def _strategy_description(strategy: StrategyManifest) -> str:
    assumptions = "; ".join(strategy.assumptions[:3])
    symbols = ", ".join(strategy.symbols)
    return (
        f"{strategy.name} is a {strategy.timeframe} strategy evaluated on {symbols}. "
        f"Public card exposes assumptions only at a summary level: {assumptions}."
    )


def _strategy_evaluation_summary(
    backtest: BacktestReport | None,
    baseline: BaselineComparisonReport | None,
    review_session: ReviewSession | None,
    arena_score: ArenaScoreReport | None,
) -> str:
    fragments = []
    if backtest is not None:
        fragments.append(
            f"Backtest return {backtest.total_return:.4f}, PF {backtest.profit_factor:.2f}, trades {backtest.trades}."
        )
    if baseline is not None:
        fragments.append(_baseline_summary(baseline) or "")
    if arena_score is not None:
        fragments.append(f"Arena score {arena_score.final_score:.1f}.")
    if review_session is not None:
        fragments.append(_review_summary(review_session) or "")
    return " ".join(fragment for fragment in fragments if fragment) or "Evaluation summary is not available yet."


def _evidence_refs(*artifacts: object | None) -> list[str]:
    refs = []
    for artifact in artifacts:
        if artifact is None:
            continue
        for attr, prefix in [
            ("thesis_id", "research_thesis"),
            ("design_id", "research_design"),
            ("session_id", "review_session"),
            ("report_id", "report"),
            ("strategy_id", "strategy"),
            ("backtest_id", "backtest"),
        ]:
            value = getattr(artifact, attr, None)
            if value:
                refs.append(f"{prefix}:{value}")
                break
    return list(dict.fromkeys(refs))


def _clip(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."
