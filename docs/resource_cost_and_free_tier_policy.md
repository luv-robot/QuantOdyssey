# Resource Cost and Free Tier Policy

This document records a rough product and engineering policy for which research actions can be
offered freely and which actions should require quota, credits, scheduling, or explicit human
approval.

The numbers below are directional. They should be recalibrated as the infrastructure, data universe,
and execution engine change.

## Principle

QuantOdyssey should make strategy thinking easy to start, but expensive evidence collection must be
budgeted.

The free experience should help a user:

```text
submit a thesis
understand whether it is structurally testable
see data requirements and gaps
run small smoke checks
compare against cached/simple baselines
receive an AI research review
```

The free experience should not allow unbounded compute-heavy search:

```text
full grid search
large optimizer sweeps
large walk-forward matrices
large Monte Carlo runs
tick/orderflow replay
wide universe scans
paid-data refreshes
```

The product promise is not "free unlimited backtesting". It is "low-friction idea intake, disciplined
evaluation, and clear upgrade points when stronger evidence is expensive".

## Current Calibration

Observed on the current small VPS during May 2026 development.

| Action | Rough cost | Free-tier fit |
| --- | ---: | --- |
| Thesis intake / pre-review | Seconds; mostly LLM tokens | Good free-tier candidate with rate limits |
| Data contract / data sufficiency check | Seconds | Good free-tier candidate |
| Cached baseline/regime summary | Seconds to under 1 minute | Good free-tier candidate if cached |
| Single smoke backtest | Seconds to tens of seconds | Good free-tier candidate with limits |
| Strategy-level Monte Carlo on existing trades | Seconds to a few minutes | Limited free quota or low-cost credits |
| Fast grid: 3 symbols x 3 timeframes x bounded trials | About 6-7 minutes; CPU near one full core | Quota/credits; not unlimited free |
| Walk-forward plus Monte Carlo follow-up | Minutes, depending on folds/trials/trades | Quota/credits; may require scheduling |
| Full grid over full history | Tens of minutes possible on small VPS | Explicit approval or paid credits |
| Top 20 universe x multiple timeframes x full grid | Tens of minutes to hours on one small node | Paid/scheduled only |
| Tick/orderflow replay | Storage and CPU can rise by an order of magnitude | Paid/high-tier only |
| Paid external data pulls | Direct cash cost plus storage | Paid/high-tier only |

Recent examples:

```text
Failed Breakout fast grid
  universe: BTC/ETH/SOL x 5m/15m/1h
  bounded trials: fast grid, max 80 trials, max 20k candles
  observed runtime: roughly 6-7 minutes
  resource profile: CPU near one full core

Failed Breakout validation follow-up
  walk-forward: 27 windows, relaxed 10-trade exploratory floor
  Monte Carlo: 608 sampled trade returns, 200 simulations, 50-trade horizon
  result: path-risk failed; useful but not promotion-grade

Full grid attempt
  universe: same 3 symbols x 3 timeframes
  max trials: 300, full history
  observed behavior: still running after several minutes with CPU near one full core
  decision: stopped as an approval-required expensive task
```

## Recommended Free Scope

Free-tier actions should be bounded, reproducible, and useful even when the user never pays.

Recommended free scope:

```text
natural-language thesis submission
AI pre-review and clarifying questions
strategy family classification
data requirement map
data availability and mismatch warning
formula/metric explanations
small smoke backtest on a narrow default sample
cached baseline board
cached market regime/context summary
one small ReviewSession summary
public strategy/library browsing
```

These features give the user a real first experience without turning free accounts into compute
farms.

## Quota Or Credit Scope

The following should be limited by monthly quota or credits:

```text
multiple candidate generation
small parameter sensitivity tests
small Monte Carlo runs
small cross-symbol checks
limited walk-forward validation
segment-aware evaluation packs
private ReviewSession deep dives
LLM-assisted strategy code generation
```

The UI should show an estimated resource class before execution:

```text
light
moderate
heavy
requires approval
```

The exact price can change later, but the user should always understand why a task is no longer a
free smoke check.

## Approval Or Paid Scope

The following should require explicit user approval, paid credits, or scheduled batch execution:

```text
full grid search
large optimizer/hyperopt runs
walk-forward matrices across many symbols/timeframes
large Monte Carlo simulations
Top 20 or wider universe scans
tick/orderflow replay
long historical data backfills
paid data provider calls
hidden replay / arena-grade validation
```

These actions are expensive because they multiply across:

```text
symbols
timeframes
parameter trials
folds
Monte Carlo simulations
trade samples
data granularity
LLM calls
```

The system should never silently run these as part of a free pre-review or default thesis submission.

## Product Rules

Default product rules:

```text
Free users can start research, but not exhaustively search.
Expensive tasks must show resource class before execution.
Full grid is not a default action.
Optimizer is evidence for robustness, not automatic alpha mining.
Monte Carlo is cheap only when trade samples already exist and the simulation count is bounded.
Tick/orderflow tests are premium validation, not baseline evidence.
Paid external data must be user-approved before refresh or use.
```

When a task is rejected or delayed for resource reasons, the product should explain the cheaper next
step:

```text
run smoke test first
reduce universe
reduce timeframe count
use cached baseline
run segment-pack evaluation before full history
wait for scheduled batch
request user approval for heavy run
```

## Harness Budget Mapping

Harness should map task types to default resource classes.

```text
light:
  thesis pre-review
  data sufficiency review
  cached baseline/regime lookup
  metric explanation

moderate:
  smoke backtest
  small Monte Carlo
  small baseline rerun
  bounded segment-pack evaluation

heavy:
  fast grid scan
  walk-forward follow-up
  cross-symbol/timeframe strategy-family validation

requires approval:
  full grid search
  large optimizer
  large Monte Carlo
  Top 20 universe scan
  tick/orderflow replay
  paid data provider run
```

The `estimated_cost` field on `ResearchTask` should be treated as a first approximation, not an
accounting system. It exists to stop runaway research and to make resource tradeoffs visible.

## Arena Implications

Arena-grade scoring is not a free smoke test.

If a strategy enters public comparison, it should pay for or be allocated a stricter validation
package:

```text
baseline comparison
walk-forward or out-of-sample checks
Monte Carlo/path-risk checks
regime or segment breakdown
search budget disclosure
reproducibility manifest
```

The public product can still show free public summaries, but private users should not expect
arena-grade validation to be free for every submitted idea.

## Open Questions

Questions to revisit before pricing:

```text
How many free smoke tests per user per month?
Should free users get cached baseline summaries only?
Should Monte Carlo be free when simulation count is very small?
How should credits price CPU-heavy work versus paid-data work?
Should failed expensive runs consume full credits or partial credits?
How should public contributions earn credits or validation discounts?
```

The current assumption is that free access is valuable for intake, learning, and light validation,
while serious evidence collection must be quota-based or paid.
