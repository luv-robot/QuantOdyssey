from __future__ import annotations

from typing import Optional

from app.models import BacktestReport, MarketSignal, ReviewCase, RiskAuditResult, StrategyManifest
from app.services.reviewer import build_review_case
from app.storage import InMemoryReviewStore, QuantRepository


def run_review_flow(
    signal: MarketSignal,
    manifest: StrategyManifest,
    risk_audit: RiskAuditResult,
    backtest_report: Optional[BacktestReport] = None,
    review_store: Optional[InMemoryReviewStore] = None,
    repository: Optional[QuantRepository] = None,
) -> ReviewCase:
    review = build_review_case(signal, manifest, risk_audit, backtest_report)
    if review_store is not None:
        review_store.add(review)
    if repository is not None:
        repository.save_review(review)
    return review
