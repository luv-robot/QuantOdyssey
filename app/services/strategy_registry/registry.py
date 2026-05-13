from __future__ import annotations

import hashlib
import re
from datetime import datetime

from app.models import (
    BacktestReport,
    BacktestStatus,
    PaperEvaluationStatus,
    PaperTradingReport,
    PaperVsBacktestComparison,
    StrategyLifecycleDecision,
    StrategyLifecycleState,
    StrategyManifest,
    StrategyRegistryEntry,
    StrategySimilarityResult,
    StrategyVersion,
)


def register_strategy(
    manifest: StrategyManifest,
    strategy_code: str,
    family: str | None = None,
    version: int = 1,
    parent_version_id: str | None = None,
) -> tuple[StrategyRegistryEntry, StrategyVersion]:
    code_hash = hashlib.sha256(strategy_code.encode("utf-8")).hexdigest()
    version_record = StrategyVersion(
        version_id=f"{manifest.strategy_id}_v{version}",
        strategy_id=manifest.strategy_id,
        version=version,
        code_hash=code_hash,
        parent_version_id=parent_version_id,
    )
    entry = StrategyRegistryEntry(
        registry_id=f"registry_{manifest.strategy_id}",
        strategy_id=manifest.strategy_id,
        name=manifest.name,
        family=family or _family_from_name(manifest.name),
        lifecycle_state=StrategyLifecycleState.GENERATED,
        current_version_id=version_record.version_id,
    )
    return entry, version_record


def should_promote_to_live_candidate(
    entry: StrategyRegistryEntry,
    backtest: BacktestReport,
    paper_report: PaperTradingReport,
    comparison: PaperVsBacktestComparison,
) -> StrategyLifecycleDecision:
    reasons: list[str] = []
    approved = True

    if backtest.status != BacktestStatus.PASSED:
        approved = False
        reasons.append("Backtest did not pass.")
    if paper_report.status != PaperEvaluationStatus.LIVE_CANDIDATE:
        approved = False
        reasons.append("Paper trading did not meet live-candidate criteria.")
    if not comparison.is_consistent:
        approved = False
        reasons.append("Paper performance is not consistent with backtest.")
    if paper_report.trades < 1:
        approved = False
        reasons.append("Paper trading generated insufficient trades.")

    return StrategyLifecycleDecision(
        strategy_id=entry.strategy_id,
        from_state=entry.lifecycle_state,
        to_state=StrategyLifecycleState.LIVE_CANDIDATE
        if approved
        else StrategyLifecycleState.RETIRED,
        approved=approved,
        reasons=reasons or ["Backtest and paper trading criteria passed."],
    )


def should_retire_strategy(
    entry: StrategyRegistryEntry,
    paper_reports: list[PaperTradingReport],
    max_consecutive_failures: int = 3,
    max_drawdown: float = -0.15,
    min_trades: int = 1,
) -> StrategyLifecycleDecision:
    reasons: list[str] = []
    recent = paper_reports[-max_consecutive_failures:]

    if len(recent) == max_consecutive_failures and all(
        report.status == PaperEvaluationStatus.RETIRED for report in recent
    ):
        reasons.append(f"Strategy failed {max_consecutive_failures} consecutive paper evaluations.")

    if paper_reports and min(report.max_drawdown for report in paper_reports) < max_drawdown:
        reasons.append("Paper drawdown exceeded retirement threshold.")

    if paper_reports and sum(report.trades for report in paper_reports) < min_trades:
        reasons.append("Paper trading generated too few trades.")

    return StrategyLifecycleDecision(
        strategy_id=entry.strategy_id,
        from_state=entry.lifecycle_state,
        to_state=StrategyLifecycleState.RETIRED if reasons else entry.lifecycle_state,
        approved=bool(reasons),
        reasons=reasons or ["No retirement criteria met."],
    )


def detect_decay(
    paper_reports: list[PaperTradingReport],
    lookback: int = 3,
    min_return_drop: float = 0.05,
) -> bool:
    if len(paper_reports) < lookback + 1:
        return False
    baseline = sum(report.total_return for report in paper_reports[:-lookback]) / (
        len(paper_reports) - lookback
    )
    recent = sum(report.total_return for report in paper_reports[-lookback:]) / lookback
    return baseline - recent >= min_return_drop


def detect_duplicate_strategy(
    strategy_id: str,
    strategy_code: str,
    compared_strategy_id: str,
    compared_code: str,
    threshold: float = 0.9,
) -> StrategySimilarityResult:
    tokens = _tokens(strategy_code)
    compared_tokens = _tokens(compared_code)
    if not tokens and not compared_tokens:
        similarity = 1.0
    else:
        similarity = len(tokens & compared_tokens) / max(1, len(tokens | compared_tokens))
    duplicate = similarity >= threshold
    return StrategySimilarityResult(
        strategy_id=strategy_id,
        compared_strategy_id=compared_strategy_id,
        similarity_score=round(similarity, 6),
        is_duplicate=duplicate,
        reasons=["Token overlap exceeded threshold."] if duplicate else ["Token overlap below threshold."],
    )


def apply_lifecycle_decision(
    entry: StrategyRegistryEntry,
    decision: StrategyLifecycleDecision,
) -> StrategyRegistryEntry:
    updates = {"lifecycle_state": decision.to_state, "updated_at": datetime.utcnow()}
    if decision.to_state == StrategyLifecycleState.LIVE_CANDIDATE:
        updates["promoted_at"] = datetime.utcnow()
    if decision.to_state == StrategyLifecycleState.RETIRED:
        updates["retired_at"] = datetime.utcnow()
        updates["retirement_reason"] = "; ".join(decision.reasons)
    return entry.model_copy(update=updates)


def _family_from_name(name: str) -> str:
    normalized = re.sub(r"V\d+$", "", name)
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", normalized)
    return "_".join(word.lower() for word in words) or normalized.lower()


def _tokens(code: str) -> set[str]:
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code))
