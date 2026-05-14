# Search Budget Policy

Search budget is part of strategy evidence.

A strategy found after heavy iterative search is less credible than a strategy that survives strict
tests with a modest search path. Logic evolution can overfit just as parameter tuning can.

Every strategy research chain should record:

```text
generated_attempts
backtest_attempts
optimizer_trials
llm_calls
human_edits
failed_variants
total_search_cost
```

Review reports should display this cost and include it in `research_overfitting_risk`.

## Governance Defaults

```yaml
harness_budget:
  max_tasks_per_day: 20
  max_backtests_per_day: 200
  max_optimizer_trials_per_strategy: 100
  max_llm_calls_per_day: 50
  max_strategy_variants_per_family_per_week: 10
```

## Kill Criteria

Research tasks should stop or downgrade when:

```text
OOS profit factor < 1.0
trade/event sample is below threshold
parameter sensitivity is excessive
hidden replay fails
strategy duplicates an existing family member
search cost is high but baseline advantage is weak
```

Search budget is not a moral penalty. It is a confidence adjustment against survivor bias.

## Low-Frequency Template Guardrail

Some strategy ideas may be conceptually strong but too rare for the current research loop. When the
event frequency is too low, the system should not compensate by adding speculative proxies, widening
definitions until the thesis changes, or launching optimizer/hyperopt on a tiny set of events.

Default response:

```text
archive the negative finding
record why the sample was insufficient
pause expensive work on that template
prefer a naturally higher-frequency strategy family for the next cycle
```

Funding Crowding Fade currently falls under this guardrail unless a future data window produces
enough real events across multiple symbols or timeframes.
