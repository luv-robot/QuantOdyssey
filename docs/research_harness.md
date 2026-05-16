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
ThesisInboxItem
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
-> ThesisInboxItem
-> ResearchHarnessCycle
```

Conversation-first intake now has its own lightweight loop:

```text
Assistant thesis submission
-> data contract / pre-review / design draft
-> intake EventEpisode
-> first ResearchFinding
-> first ResearchTask queue
-> scratchpad trace
```

This loop does not claim the thesis is valid and does not run expensive tests automatically. Its job
is to turn a raw idea into a supervised backlog that can ask: do we have the right data, enough
events, a matched baseline, and a sane evaluation profile?

`ThesisInboxItem` is the proactive communication layer. Harness may suggest ideas from baselines,
regime shifts, failure findings, data gaps, watchlist candidates, and ReviewSession next experiments.
These items remain `suggested` until the human accepts, edits, rejects, archives, or converts them
into official theses/tasks.

`ResearchScratchpadEvent` is the chronological audit layer. Harness and future agents should append
tool calls, LLM calls, budget decisions, task creation, backtest outputs, ReviewSessions, and findings
to `.qo/scratchpad/<run_id>.jsonl` so a research run can be replayed after the fact.

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

## Agent Quality Supervision

Agent Eval Suite tests whether the AI research system itself obeys research discipline. It is
admin-facing quality control, not a strategy edge detector.

```text
AgentEvalCase
-> AgentEvalCaseResult
-> AgentEvalRun
-> Agent Quality Console / Supervisor Chat
```

The Supervisor may flag ReviewSessions, ResearchTasks, prompts, skills, or scratchpad traces for
human review. It cannot promote strategies, publish private artifacts, change risk budgets, or bypass
Harness budget controls.

## Unattended Maintenance Tasks

When `HARNESS_RUNNER_SEED_MAINTENANCE_TASKS=true`, the scheduled Harness runner seeds one bounded
daily queue for low-risk evidence collection:

- data sufficiency review
- baseline board rerun
- baseline-implied / OHLCV regime bucket review
- Failed Breakout walk-forward and Monte Carlo follow-ups when a replayable universe report exists
- strategy-level Monte Carlo follow-ups for a small number of recent backtests

These tasks are daily-idempotent, low-autonomy, and still pass through Harness budget guardrails. They
are meant to keep the private mining machine collecting evidence while the user is away; they should
not launch large optimizer searches or new alpha-generation campaigns.
