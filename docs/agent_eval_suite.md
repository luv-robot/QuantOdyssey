# Agent Eval Suite

Agent Eval Suite tests the AI research system itself.

It does not decide whether a strategy has alpha. It tests whether the agents obey research discipline:

- Reviewer should not approve a strategy that fails matched baselines.
- Harness should not spend optimizer budget on tiny samples.
- Researcher should reject future leakage.
- Reviewer should distinguish data gaps from strategy failure.
- Optimizer wins should be treated as fragile when neighboring cells collapse.

## Product Layer

The product expression should be admin-only:

```text
Agent Quality Console
-> AgentEvalRun
-> AgentEvalCaseResult
-> flagged ReviewSession / ResearchTask / Scratchpad trace
-> Supervisor Chat
```

Ordinary users should only see simplified trust signals:

```text
AI Review QA: passed / flagged
Evidence Quality: sufficient / weak / missing
Needs Human Review: yes / no
```

The global Supervisor Agent may read eval results and internal traces, but it cannot promote
strategies, change risk budgets, publish private artifacts, or bypass Harness budgets.

## MVP Command

```bash
python scripts/run_agent_eval_suite.py
```

Pass a JSON mapping of `case_id -> response` to score real outputs:

```bash
python scripts/run_agent_eval_suite.py --responses agent_responses.json --json
```
