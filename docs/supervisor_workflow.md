# Supervisor Workflow

Supervisor is the global admin quality-control layer for QuantOdyssey.

It watches the research machine, not the market. Its job is to identify whether agents, prompts,
skills, budgets, or reviews are behaving badly enough to require human attention.

## Inputs

```text
AgentEvalRun
ReviewSession
ResearchTask
ResearchFinding
ResearchScratchpadEvent
HealthReport
```

The MVP uses the first four inputs. Scratchpad and HealthReport can be attached as richer evidence
links later.

## Outputs

```text
SupervisorReport
SupervisorFlag
recommended_next_actions
```

Flag types:

- `agent_eval_failure`
- `review_session_risk`
- `task_budget_risk`
- `data_gap`
- `system_note`

Severity:

- `info`
- `warn`
- `critical`

## Product Surface

Admin-only:

- Agent Quality Console
- Supervisor Chat
- Eval case details
- Supervisor flags
- links to ReviewSession, ResearchTask, ResearchFinding, and scratchpad traces

User-facing:

- AI Review QA: passed / flagged
- Evidence Quality: sufficient / weak / missing
- Needs Human Review: yes / no

## Boundaries

Supervisor may:

- flag suspicious ReviewSessions
- recommend pausing a prompt, skill, or model route
- recommend narrowing a ResearchTask
- ask for human review
- create quality-control summaries

Supervisor may not:

- approve paper/live promotion
- change risk budgets
- publish private artifacts
- delete user research assets
- bypass Harness budget guardrails

## Commands

```bash
python scripts/run_agent_eval_suite.py
python scripts/run_supervisor_quality_check.py
```

The first command evaluates agent behavior. The second persists an `AgentEvalRun` and a
`SupervisorReport` for the Dashboard.
