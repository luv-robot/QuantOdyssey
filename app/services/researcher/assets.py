from __future__ import annotations

from app.models import (
    BacktestReport,
    BaselineComparisonReport,
    MarketRegimeSnapshot,
    ResearchAssetIndexEntry,
    ResearchThesis,
    RobustnessReport,
    StrategyCandidate,
)


def build_research_asset_index_entry(
    thesis: ResearchThesis,
    candidate: StrategyCandidate,
    backtest: BacktestReport,
    baseline: BaselineComparisonReport,
    robustness: RobustnessReport,
    regime: MarketRegimeSnapshot,
    review_case_id: str | None,
) -> ResearchAssetIndexEntry:
    manifest = candidate.manifest
    tags = list(
        dict.fromkeys(
            [
                "human_led_research",
                regime.primary_regime.value,
                candidate.template_name,
                "passed" if robustness.passed else "needs_review",
            ]
        )
    )
    return ResearchAssetIndexEntry(
        asset_id=f"asset_{backtest.backtest_id}",
        asset_type="strategy_research_bundle",
        title=f"{thesis.title} / {manifest.name}",
        thesis_id=thesis.thesis_id,
        signal_id=manifest.signal_id,
        strategy_id=manifest.strategy_id,
        tags=tags,
        summary=(
            f"Candidate score {candidate.score:.2f}; return {backtest.total_return:.4f}; "
            f"profit factor {backtest.profit_factor:.2f}; robustness {robustness.robustness_score:.2f}; "
            f"best baseline {baseline.best_baseline_name}."
        ),
        linked_artifacts={
            "backtest_id": backtest.backtest_id,
            "baseline_report_id": baseline.report_id,
            "robustness_report_id": robustness.report_id,
            "regime_id": regime.regime_id,
            **({"review_case_id": review_case_id} if review_case_id else {}),
        },
    )
