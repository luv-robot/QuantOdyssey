---
name: funding_crowding_fade
description: Test funding and open-interest crowding fade hypotheses only when event frequency is sufficient.
minimum_data_level: L1_FUNDING_OI
---

# Funding Crowding Fade

Core thesis:

Extreme funding plus elevated open interest can mark crowded positioning, but it becomes tradable
only when price extension fails and crowding begins to unwind.

Required evidence:

- funding_rate
- funding_percentile
- open_interest
- open_interest_percentile
- price_extension
- failed_breakout or failed_breakdown
- OI change after failure
- matched event baselines

Baselines:

- no_trade_baseline
- funding_extreme_only_baseline
- funding_plus_OI_baseline
- random_entry_in_funding_extreme_window
- opposite_direction_baseline
- simple_failed_breakout_baseline

Guardrails:

- Funding extremes alone are not entries.
- Do not optimize on tiny event samples.
- If candles are restricted to OI overlap and sample collapses, record a data/sampling finding.
- Pause expensive work until cross-symbol event frequency is sufficient.

Default next experiments:

- cross-symbol event-frequency scan
- event-definition sensitivity
- event-level baseline replacement
- regime bucket review
