# Dashboard Assistant

QuantOdyssey uses a two-part assistant interaction:

- The input stays at the bottom of the page, similar to Codex.
- Long answers render in the `Assistant Workspace` in the middle column of `Research Workbench`.

This keeps the command surface always available while giving substantial answers enough room.

## LLM Provider

The first production provider is DeepSeek through an OpenAI-compatible chat completions endpoint.

Required:

```bash
DEEPSEEK_API_KEY=
```

Optional:

```bash
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_API_BASE=https://api.deepseek.com
```

If `DEEPSEEK_API_KEY` is missing or the API call fails, the assistant falls back to a rule-based
internal router. The fallback can still point users to pages such as `Research Workbench`,
`Run Detail`, `Strategy Catalog`, `Metric Audit`, and `System Status`.

## Thesis Intake Action

When the bottom input receives a complete thesis submission, the assistant routes it through a local
action instead of sending the full thesis text to DeepSeek. This action creates:

- `ResearchThesis`
- `ThesisDataContract`
- `ThesisPreReview`
- `ResearchDesignDraft`
- `EventEpisode`
- first-pass `ResearchFinding`
- first-pass `ResearchTask` queue
- `.qo/scratchpad` trace

This is not a strategy run. It is the pre-research gate that asks whether the idea is structured,
whether the requested timeframe/data can be supported, and which baseline/event-frequency/regime
tests should come before code generation.

## Logging

Every assistant request is stored as:

- `prompt_logs`
- `model_response_logs`

The logs record the model route, prompt version, question, compact dashboard context, answer, and
whether the LLM response parsed successfully.

## Privacy Boundary

The first version sends only compact dashboard context to the LLM:

- recent thesis titles/status
- recent harness task summaries
- regime scores
- baseline board summary
- latest ReviewSession identifiers/scores
- catalog counts

Do not send full private strategy code, exchange secrets, API keys, or complete alpha parameter sets
without an explicit user consent layer.
