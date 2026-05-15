# Research Scratchpad

Research Scratchpad is the append-only trace for a single research run.

It is intentionally separate from the main research asset tables:

- Postgres stores structured assets that the product can query.
- Scratchpad stores the chronological work trail that explains how the run happened.

Default path:

```text
.qo/scratchpad/<run_id>.jsonl
```

Each line is a `ResearchScratchpadEvent`:

```json
{
  "event_id": "scratch_run_001_abcd1234",
  "run_id": "run_001",
  "event_type": "research_task",
  "payload": {},
  "task_id": "task_001",
  "thesis_id": "thesis_001",
  "strategy_id": "strategy_001",
  "evidence_refs": ["review_session:review_001"],
  "created_at": "2026-05-15T00:00:00Z"
}
```

The scratchpad is useful for:

- debugging agent runs
- replaying why a task was generated
- auditing tool calls and LLM calls
- inspecting budget decisions
- building admin-only Supervisor views

It should never contain secrets, exchange credentials, wallet keys, or private API tokens.
