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

Supervisor now consumes `HealthReport` directly, so infrastructure failures can become first-class
quality flags instead of hiding in container logs.

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
- `system_health_failure`
- `automation_failure`
- `notification_failure`
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
- flag database, orderflow, Prefect, n8n, Qdrant, disk, and webhook-secret failures
- send structured alert payloads to user and developer-agent channels through webhooks
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
python scripts/run_supervisor_system_monitor.py
```

The first command evaluates agent behavior. The second persists an `AgentEvalRun` and a
`SupervisorReport` for the Dashboard. The third runs system health checks, persists a
`SupervisorReport`, and sends a bounded alert when critical system failures appear.

## System Alerts

The VPS runs `scripts/prefect_supervisor_monitor_flow.py` as `supervisor-monitor-scheduler`.
Default cadence:

```text
SUPERVISOR_MONITOR_CRON=*/15 * * * *
```

Alert behavior:

- critical system flags alert immediately unless an identical alert was sent recently
- repeated identical alerts are suppressed for `SUPERVISOR_ALERT_REPEAT_MINUTES` minutes
- warn-only alerts are persisted, but not pushed unless `SUPERVISOR_ALERT_ON_WARN=true`
- payloads are sent to `SUPERVISOR_ALERT_WEBHOOK_URL`
- optional developer-agent payloads are sent to `SUPERVISOR_DEV_AGENT_WEBHOOK_URL`

Default VPS webhook:

```text
http://n8n:5678/webhook/supervisor-system-alert
```

The bundled n8n workflow returns a `mailto:` handoff for `SUPERVISOR_ALERT_EMAIL_TO` and a structured
`dev_agent_handoff`. Fully automatic push delivery still requires adding SMTP, Telegram, Feishu, or
another credential inside n8n.
