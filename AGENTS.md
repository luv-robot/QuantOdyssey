# AGENTS.md

# Quant Agent Platform — Agent Operating Specification

This document defines:

- Agent responsibilities
- Allowed actions
- Forbidden actions
- Data contracts
- State transitions
- Safety rules
- Communication standards

All agents MUST follow this specification.

---

# Codex Cloud Quickstart

Cloud agents working on this repository should use Python 3.11.

Setup:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

If package-index access is blocked in Codex Cloud, use the no-build-isolation fallback:

```bash
pip install --no-build-isolation -e ".[dev]"
```

Verification:

```bash
python -m pytest
```

Current expected result:

```text
87 passed
```

Do not commit generated runtime data:

```text
.venv/
.venv311/
.tools/
logs/
schemas/
*.sqlite3
freqtrade_user_data/data/
freqtrade_user_data/backtest_results/
freqtrade_user_data/strategies/*.py
```

Use `codex/*` branches for cloud-agent work. Do not push directly to `main` unless the user
explicitly asks. All PRs should pass GitHub Actions CI before deployment.

See [docs/cloud_development.md](docs/cloud_development.md) for the full cloud and multi-agent
workflow.

---

# Core Principles

## 1. Agents Are Specialized

Each agent has:

- A narrow responsibility
- Defined inputs
- Defined outputs
- Explicit limitations

No agent should perform tasks outside its scope.

---

## 2. Everything Must Be Structured

All communication between agents MUST use:

- Pydantic models
- Structured JSON
- Typed schemas

No free-form inter-agent communication.

---

## 3. Every Decision Must Be Auditable

The system MUST preserve:

- Prompts
- LLM responses
- Strategy versions
- Risk findings
- Backtest reports
- Review summaries

No hidden reasoning.

---

## 4. Human Approval Is Mandatory

No strategy may:

- enter live trading
- allocate capital
- modify leverage
- modify risk limits

without explicit human approval.

---

# Global Workflow

```text
Scout
  ↓
Researcher
  ↓
Risk Auditor
  ↓
Backtester
  ↓
Reviewer
  ↓
RAG Knowledge Base

Global State Machine
NEW_SIGNAL
→ RESEARCH_REQUESTED
→ STRATEGY_GENERATED
→ RISK_AUDITING
→ RISK_APPROVED / RISK_REJECTED
→ BACKTEST_RUNNING
→ BACKTEST_PASSED / BACKTEST_FAILED
→ REVIEW_COMPLETED
→ PAPER_TRADING
→ LIVE_APPROVED
→ RETIRED

Agents may ONLY transition states they explicitly own.

Agent Definitions
1. Market Scout
Responsibility

Detect market anomalies and produce structured signals.

Inputs
OHLCV
Funding rate
Open interest
Liquidation data
Orderbook data
Outputs

MarketSignal

Allowed Actions
Pull market data
Calculate indicators
Detect anomalies
Rank opportunities
Forbidden Actions
Generate strategies
Execute trades
Modify portfolio
Change risk parameters
Required Output
{
  "signal_id": "signal_001",
  "symbol": "BTC/USDT",
  "signal_type": "volume_spike",
  "rank_score": 81
}
2. Strategy Researcher
Responsibility

Generate candidate trading strategies.

Inputs
MarketSignal
Historical cases from RAG
Existing strategy templates
Outputs
strategy.py
StrategyManifest
assumptions.md
failure_modes.md
Allowed Actions
Query vector database
Generate strategy logic
Generate indicators
Generate entry/exit logic
Forbidden Actions
Execute backtests
Approve risk
Execute trades
Allocate capital
Mandatory Requirements

Every strategy MUST:

include stoploss
define timeframe
define exit conditions
include assumptions
include failure modes
3. Risk Auditor
Responsibility

Prevent dangerous or invalid strategies from entering execution.

Inputs
strategy.py
StrategyManifest
Outputs

RiskAuditResult

Allowed Actions
Static code analysis
Risk rule validation
Reject unsafe strategies
Forbidden Actions
Generate strategies
Modify market signals
Execute trades
Mandatory Checks

The auditor MUST reject:

martingale logic
unlimited DCA
missing stoploss
excessive leverage
lookahead bias
future leakage
unrestricted position sizing
Example Output
{
  "approved": false,
  "findings": [
    {
      "severity": "high",
      "message": "Missing stoploss"
    }
  ]
}
4. Backtest Specialist
Responsibility

Execute strategy backtests using Freqtrade.

Inputs
Approved strategy
Historical data
Outputs

BacktestReport

Allowed Actions
Execute Freqtrade CLI
Parse backtest results
Export metrics
Forbidden Actions
Generate strategies
Modify strategy logic
Execute live trades
Required Metrics
Sharpe ratio
Max drawdown
Profit factor
Win rate
Total return
Trade count
5. Reviewer Agent
Responsibility

Analyze completed backtests and extract lessons.

Inputs
BacktestReport
trades.json
MarketSignal
Outputs

ReviewCase

Allowed Actions
Summarize failures
Detect recurring patterns
Update vector knowledge base
Forbidden Actions
Execute trades
Modify strategies
Approve deployment
Primary Goal

Transform failed strategies into reusable knowledge.

6. PM Agent / Orchestrator
Responsibility

Manage workflow state transitions.

Inputs
Agent outputs
Human approvals
Workflow events
Outputs
Task routing
State updates
Notifications
Allowed Actions
Trigger workflows
Retry failed jobs
Queue tasks
Notify operators
Forbidden Actions
Generate alpha
Modify strategy logic
Override risk decisions
Communication Rules
Required Format

All agents MUST communicate using:

Pydantic BaseModel

or:

JSON schema

Non-Retryable Errors

Do NOT retry:

invalid strategy
missing stoploss
malformed schema
failed risk audit
Risk Rules
Global Safety Constraints

These rules override ALL agents.

Forbidden

The platform MUST NEVER:

remove stoploss automatically
increase leverage automatically
average down infinitely
deploy directly to live trading
bypass human approval
dynamically execute remote code
Human Approval Gates

Human approval is required for:

paper trading promotion
live trading promotion
leverage changes
capital allocation changes
RAG Knowledge Base Rules

The RAG database stores:

successful patterns
failed patterns
market conditions
strategy assumptions
postmortem analysis

The RAG database MUST NOT store:

raw API secrets
credentials
exchange private keys
LLM Usage Policy
LLMs Are Research Tools

LLMs are hypothesis generators.

LLMs are NOT trusted trading engines.

Every LLM-generated strategy MUST pass:

static validation
risk audit
historical backtest
human review

MVP

MVP deployment scope:

local Docker deployment
paper trading only
Binance test environment
manual approval required
Production (Future)

Future production targets:

Temporal workflows
distributed workers
multi-exchange execution
portfolio risk engine
GPU research cluster


Security Rules

Secrets MUST NEVER:

appear in prompts
appear in logs
enter vector databases
be committed to git

Use:

.env
Docker secrets
secret manager
Final Principle

The purpose of this system is NOT:

fully autonomous trading.

The purpose is:

scalable quantitative research augmentation.

The system should help humans:

discover opportunities
validate hypotheses
reduce repetitive work
accumulate market knowledge
improve research efficiency

NOT remove human judgment.
