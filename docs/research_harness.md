# Research Harness

Research Harness is responsible for autonomous research progress. It does not trade.

It reads structured evidence:

```text
BacktestReport
OptimizationResult
MonteCarloBacktestReport
ReviewCase
RegimeBucketStats
MissedOpportunityReport
PaperTradingReport
```

It emits structured artifacts:

```text
ResearchTask
ResearchFinding
WeeklyResearchDigest
StrategyLifecycleRecommendation
```

## Work Loop

```text
Hypothesis Generator
-> Experiment Designer
-> Strategy Coder
-> Static Auditor
-> Backtest Runner
-> Backtest Analyst
-> Reviewer
-> Next-task Planner
```

Subagents are quality-control stations, not an open-ended chat room. They exchange Pydantic models
instead of free-form opinions.

## ResearchTask Contract

Every autonomous suggestion must become a task:

```text
hypothesis
rationale
required_experiments
success_metrics
failure_conditions
estimated_cost
priority_score
status
```

The Harness may automatically generate and run low-risk research experiments, but paper promotion,
live trading, risk-budget changes, and any capital decision require human approval.

## Autonomy Levels

```text
L0: write suggestions only
L1: generate ResearchTask, human approval required
L2: run low-risk experiments automatically
L3: generate findings and next tasks automatically
L4: recommend promotion or retirement
L5: paper/live/capital remains human-gated
```
