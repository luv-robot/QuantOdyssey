# Thesis Inbox and Public Library

QuantOdyssey needs two idea-supply loops:

1. Harness should proactively suggest research ideas so the human researcher is not the bottleneck.
2. Future users need public examples so they do not start from an empty workspace.

Both loops are private-first. Machine suggestions do not become accepted theses automatically, and public cards never expose private alpha details.

## Thesis Inbox

`ThesisInboxItem` is the handoff object between autonomous Harness evidence and human thesis acceptance.

Sources:

- `human_seeded`
- `baseline_derived`
- `regime_derived`
- `failure_derived`
- `review_session_derived`
- `data_gap_derived`
- `watchlist_derived`
- `machine_seeded`

Statuses:

- `suggested`
- `viewed`
- `accepted`
- `edited`
- `rejected`
- `archived`
- `converted_to_thesis`
- `converted_to_task`

The Harness may create `suggested` items automatically. A user must accept, edit, or convert them before they become official `ResearchThesis` objects.

## Public Library

The public library consists of redacted cards:

- `PublicThesisCard`
- `PublicStrategyCard`

Public cards may show:

- strategy family
- thesis summary
- market observation summary
- data requirements
- baseline summary
- regime notes
- public metrics
- public Arena labels
- next experiments

Public cards must not show:

- complete strategy code
- exact parameters
- full trade logs
- private prompt logs
- model responses
- complete private AI review commentary
- private failure path notes

Visibility levels:

- `private`
- `unlisted`
- `public`
- `arena_submitted`

Nothing is public by default. Publishing should follow:

```text
private artifact
-> public card draft
-> redaction check
-> user approval
-> published public library item
```

## Scripts

Generate Harness suggestions:

```bash
python scripts/run_harness_inbox_suggestions.py
```

Export published public cards:

```bash
python scripts/export_public_library.py --output public/library.json
```

## Product Role

The Thesis Inbox accelerates private research. The Public Library accelerates user onboarding.

They connect, but they should never collapse into one system: private ideas stay private unless a user explicitly publishes a redacted card.
