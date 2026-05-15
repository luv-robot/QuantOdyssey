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
