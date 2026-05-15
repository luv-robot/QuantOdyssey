---
name: failed_breakout_punishment
description: Test failed-breakout reversal ideas around visible key levels and acceptance failure.
minimum_data_level: L0_OHLCV_ONLY
---

# Failed Breakout Punishment

Core thesis:

Visible key-level breakouts that quickly return inside the prior range may trap breakout followers
and create short-horizon reversal pressure.

Minimum event definition:

- key_level_type
- level_quality_score
- breakout_depth_bps
- time_outside_level
- return_inside_level
- volume_zscore
- max_holding_time
- stop_loss

Baselines:

- no_trade_baseline
- breakout_only_baseline
- failed_breakout_simple_baseline
- random_entry_in_breakout_window
- opposite_direction_baseline
- key_level_only_baseline

Failure conditions:

- breakout acceptance persists beyond max_acceptance_time
- trend regime is strong and not exhausted
- sample count is below floor
- edge disappears across symbols or timeframes

Default next experiments:

- event-frequency scan across BTC/ETH/SOL
- parameter sensitivity over acceptance windows and breakout depth
- regime bucket review
- orderflow acceptance validation when data exists
