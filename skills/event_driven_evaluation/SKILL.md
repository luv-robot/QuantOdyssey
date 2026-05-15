---
name: event_driven_evaluation
description: Evaluate low-frequency or event-triggered strategy families by event quality instead of continuous runtime returns.
minimum_data_level: L0_OHLCV_ONLY
---

# Event-Driven Evaluation

Use this skill when a strategy thesis depends on discrete market events.

Required evidence:

- event_count
- trigger_count
- trade_count
- event_hit_rate
- average_R
- event_profit_factor
- max_adverse_excursion
- false_positive_cost
- baseline comparison over the same event windows

Guardrails:

- Do not rank by annualized return alone.
- Do not use Sharpe as the primary metric when trade count is tiny.
- If event_count or trade_count is below the declared sample floor, produce a data/sample finding
  before strategy promotion.
- If baseline advantage is weak, recommend pause, reformulation, or a higher-frequency family.

Output:

- ResearchFinding
- ResearchTask for next experiment
- ReviewSession evidence_for/evidence_against update
