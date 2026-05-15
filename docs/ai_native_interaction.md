# AI-Native Interaction

QuantOdyssey should gradually move from click-heavy dashboards to conversation-driven workflows.
The target pattern is closer to Codex or Claude Code than to a traditional analytics console:
the user states an intent, the AI converts it into structured settings, validates data and risk,
then exposes the resulting artifacts for inspection.

## Principle

Conversation is the primary control surface. UI components are inspection, correction, and approval surfaces.

The user should be able to say:

```text
Test daily BTC RSI divergence, long-only, OHLCV only, with stoploss.
```

The system should derive:

```text
ResearchThesis
ThesisDataContract
Data requirements
Candidate strategy settings
Backtest mode
Review questions
Next actions
```

## Interaction Pattern

1. User describes the goal in natural language.
2. AI drafts structured fields and data requirements.
3. System runs a data contract check before experiments.
4. User corrects or approves the draft.
5. Harness executes the workflow and reports progress.
6. AI links the user to artifacts that already exist in the product.

## Implemented V1

The global dashboard assistant can now accept a complete natural-language thesis directly from the
bottom input. When the message looks like a thesis submission, the system handles it locally rather
than sending the full text to an external LLM:

```text
assistant message
-> ResearchThesis
-> ThesisDataContract
-> ThesisPreReview
-> ResearchDesignDraft
-> EventEpisode
-> ResearchFinding
-> ResearchTask queue
-> ResearchHarnessCycle
-> .qo/scratchpad intake trace
```

The first Harness task queue is intentionally research-oriented. It creates baseline, data
sufficiency, event-frequency, or regime-bucket tasks before strategy code generation. This keeps the
workflow focused on improving research quality rather than immediately optimizing a variant.

## Guardrails

- Natural language can fill fields, but cannot bypass data contracts.
- Selected MarketSignals are evidence, not authority over thesis timeframe or data needs.
- If a selected signal conflicts with the thesis, the system must block or create a thesis-seed context.
- AI may recommend actions, but paper/live/capital decisions remain human-gated.

## Migration Targets

- Thesis submission: conversation-first, with editable structured draft.
- Data downloads: user asks for coverage; AI prepares symbols, timeframes, and cost/risk notes.
- Research pipeline: user asks for a run; AI shows data contract, budget, and expected artifacts.
- ReviewSession: user asks follow-up questions; AI cites backtests, baselines, robustness, and review cases.
- Supervisor: admin-only dialogue for system quality, missing data, bad metrics, and repeated failure loops.
