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
ResearchHarnessCycle
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

MVP implementation:

```text
HumanResearchPipelineResult
-> ReviewSession
-> ResearchFinding
-> ResearchTask
-> ResearchHarnessCycle
```

The first MVP does not execute expensive optimizer/hyperopt jobs automatically. It records bounded
`parameter_sensitivity_test` tasks and marks larger search runs as approval-required. Optimizer is
for robustness evidence, not alpha discovery or automatic strategy rewriting.

The Harness may automatically generate and run low-risk research experiments, but paper promotion,
live trading, risk-budget changes, and any capital decision require human approval.

## Strategy Family Scope Control

Harness must not keep spending research budget on a strategy family only because the narrative is
interesting. If a bounded universe scan shows that a template cannot produce enough valid events,
the correct next action is to pause or downgrade that template, not to invent lower-quality proxy
data or run optimizer over a tiny sample.

For Funding Crowding Fade specifically:

```text
if cross-market event-definition scan has no robust trial ids
and no best trial meets the sample floor:
  pause optimizer / hyperopt
  do not add synthetic or narrative-only data proxies
  summarize the negative result
  switch the next Harness cycle toward naturally higher-frequency strategy families
```

This does not mean the thesis is false forever. It means the current research budget should move to
strategies where the market produces enough repeatable observations to test.

## Autonomy Levels

```text
L0: write suggestions only
L1: generate ResearchTask, human approval required
L2: run low-risk experiments automatically
L3: generate findings and next tasks automatically
L4: recommend promotion or retirement
L5: paper/live/capital remains human-gated
```
