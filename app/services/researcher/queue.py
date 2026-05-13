from __future__ import annotations

from datetime import datetime

from app.models import (
    ExperimentQueueItem,
    ExperimentQueueStatus,
    MonteCarloBacktestConfig,
    StrategyCandidate,
)
from app.services.backtester import estimate_monte_carlo_cost


def build_experiment_queue_item(
    candidate: StrategyCandidate,
    config: MonteCarloBacktestConfig | None,
    approved_expensive_run: bool,
) -> ExperimentQueueItem:
    config = config or MonteCarloBacktestConfig()
    estimated_cost = estimate_monte_carlo_cost(config)
    needs_approval = estimated_cost > config.expensive_simulation_threshold
    status = (
        ExperimentQueueStatus.AWAITING_APPROVAL
        if needs_approval and not approved_expensive_run
        else ExperimentQueueStatus.APPROVED
    )
    reason = (
        "Monte Carlo cost exceeds threshold; human approval required."
        if status == ExperimentQueueStatus.AWAITING_APPROVAL
        else "Experiment is within configured resource limits."
    )
    return ExperimentQueueItem(
        queue_id=f"queue_{candidate.candidate_id}",
        thesis_id=candidate.manifest.thesis_id,
        signal_id=candidate.manifest.signal_id,
        strategy_id=candidate.manifest.strategy_id,
        candidate_id=candidate.candidate_id,
        status=status,
        reason=reason,
        estimated_cost=estimated_cost,
        approved_by="system" if status == ExperimentQueueStatus.APPROVED else None,
    )


def mark_experiment_queue_completed(item: ExperimentQueueItem) -> ExperimentQueueItem:
    return item.model_copy(
        update={
            "status": ExperimentQueueStatus.COMPLETED,
            "completed_at": datetime.utcnow(),
        }
    )
