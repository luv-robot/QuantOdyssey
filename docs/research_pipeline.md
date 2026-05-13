# Human-Led Research Pipeline

QuantOdyssey treats strategy research as a human-led thesis validation loop.

The current research direction is defined by three companion specs:

- [Research OS](research_os.md): research philosophy, strategy families, data sufficiency, market context, and watchlist policy.
- [Evaluation Profiles](evaluation_profiles.md): strategy evaluation types, event episodes, baselines, Monte Carlo policy, and promotion states.
- [Harness Researcher](harness_researcher.md): evidence-driven research loop, task generation, failure summarization, and data collection policy.

The intended flow is:

```text
Human Research Thesis
-> thesis pre-review
-> research design draft
-> inferred strategy_family / evaluation_type / data_sufficiency_level
-> linked MarketSignal / MarketContext
-> event episodes when applicable
-> 3-5 strategy candidates
-> static risk audit
-> backtest
-> backtest reliability validation
-> Monte Carlo backtesting
-> review case
-> watchlist / deeper research / rejected thesis
-> Harness evidence pack and next research tasks
```

The agent is responsible for implementation scaffolding, test orchestration, and audit trails. It
is not treated as an autonomous alpha source. Harness is a research assistant, not a trader: it
pushes failure summarization, market data collection, and the next research loop, but it does not
produce investment plans or capital allocation decisions.

## Dashboard

Open the Dashboard and use the `Research Pipeline` tab:

```text
https://quantodyssey.com
```

The form requires a thesis title, market observation, hypothesis, and trade logic. It uses an
existing `MarketSignal` from the database and persists every generated research asset.

Use `Research Run Detail` to inspect each thesis after execution. It links the thesis to generated
strategies, static risk audit, Freqtrade backtest, reliability validation, Monte Carlo, trade
summary, enhanced review metrics, and review failure reasons.

Candidate generation is human-led. The human thesis is the source of the strategy idea, while the
agent turns it into several implementation variants. Current variants include volume/momentum,
trend confirmation, and volatility breakout templates. Before generating candidates, the pipeline
retrieves recent enhanced review metrics for the linked signal and injects reusable lessons as
historical constraints, so repeated failures become part of the next implementation context.

For event-driven strategies, success is evaluated by event episodes and type-matched baselines, not
only by time-window return. Low-frequency strategies with insufficient samples should enter
Watchlist instead of being treated as failed.

Before implementation, the thesis should pass through Pre-Review. Pre-Review checks whether the
structure is complete, conditions are testable, and the idea is close to common public strategies or
indicator stacking. It asks at most three core questions and records assumptions if the user chooses
to continue without answering.

## CLI

On the VPS:

```bash
cd /home/codexboy/QuantOdyssey
docker compose -f docker-compose.vps.yml exec -T app python scripts/run_human_research_pipeline.py \
  --title "Volume continuation smoke test" \
  --market-observation "BTC volume expands above its rolling baseline." \
  --hypothesis "Continuation odds improve when volume confirms momentum." \
  --trade-logic "Enter long on volume and RSI confirmation; exit on momentum exhaustion." \
  --expected-regime "trend continuation" \
  --invalidation-condition "fails after fee and slippage validation"
```

Large Monte Carlo runs are gated. Pass `--approve-expensive-monte-carlo` only after reviewing the
simulation size.

By default the pipeline runs real Freqtrade backtests. For local flow testing only, use:

```bash
--backtest-mode mock
```
