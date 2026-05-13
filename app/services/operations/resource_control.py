from __future__ import annotations

from app.models import MonteCarloBacktestConfig, ResourceBudgetReport, StrategyCandidate
from app.services.backtester import estimate_monte_carlo_cost


def evaluate_resource_budget(
    candidate: StrategyCandidate,
    config: MonteCarloBacktestConfig | None,
    approved_expensive_run: bool,
) -> ResourceBudgetReport:
    config = config or MonteCarloBacktestConfig()
    estimated_cost = estimate_monte_carlo_cost(config)
    requires_approval = estimated_cost > config.expensive_simulation_threshold
    approved = not requires_approval or approved_expensive_run
    findings = [
        f"Estimated Monte Carlo cost is {estimated_cost}.",
        f"Configured threshold is {config.expensive_simulation_threshold}.",
    ]
    if requires_approval and not approved_expensive_run:
        findings.append("Human approval is required before expensive simulation can run.")
    return ResourceBudgetReport(
        report_id=f"resource_budget_{candidate.candidate_id}",
        candidate_id=candidate.candidate_id,
        strategy_id=candidate.manifest.strategy_id,
        estimated_monte_carlo_cost=estimated_cost,
        max_allowed_cost=config.expensive_simulation_threshold,
        approved=approved,
        requires_human_approval=requires_approval,
        findings=findings,
    )
