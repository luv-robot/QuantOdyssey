# Execution Integration

QuantOdyssey 当前是研究为主的平台，但必须预留与实际下单系统连接的结构和关键接口。

核心原则：

```text
Research platform produces evidence and deployment candidates.
Execution system produces orders.
```

QuantOdyssey 不直接连接交易所实盘账户，不持有交易 API secret，不绕过人工审批。它只输出可审计、可回放、可拒绝的研究资产和部署候选。

## System Boundary

```text
QuantOdyssey Research Platform
  -> thesis validation
  -> strategy implementation
  -> risk audit
  -> backtest / walk-forward / Monte Carlo
  -> paper research report
  -> failure review
  -> deployment candidate package

Execution System
  -> account state
  -> portfolio constraints
  -> order sizing
  -> exchange connectivity
  -> order routing
  -> fills / positions
  -> live risk controls
  -> kill switch
```

The integration point is a signed or versioned `DeploymentCandidate`, not a direct order.

## Promotion Boundary

QuantOdyssey may promote a strategy to research states such as:

```text
WATCHLIST
ROBUST_ENOUGH_FOR_DEEPER_TEST
PAPER_RESEARCH_CANDIDATE
DEPLOYMENT_CANDIDATE
```

`DEPLOYMENT_CANDIDATE` does not mean “trade this automatically”. It means the research system has produced enough structured evidence for a separate execution review.

## DeploymentCandidate

Recommended payload:

```json
{
  "candidate_id": "deploy_001",
  "strategy_id": "strategy_001",
  "strategy_version": "v3",
  "strategy_family": "failed_breakout_punishment",
  "evaluation_type": "event_driven_alpha",
  "created_at": "2026-05-13T00:00:00Z",
  "research_status": "DEPLOYMENT_CANDIDATE",
  "data_sufficiency_level": "L0",
  "approved_symbols": ["BTC/USDT", "ETH/USDT"],
  "approved_timeframes": ["5m"],
  "expected_regimes": ["NORMAL"],
  "blocked_regimes": ["STRONG_TREND", "CRASH", "CHAOS"],
  "evidence_refs": {
    "thesis_id": "thesis_001",
    "backtest_report_ids": ["bt_001"],
    "validation_suite_ids": ["val_001"],
    "monte_carlo_ids": ["mc_001"],
    "review_case_ids": ["review_001"]
  },
  "risk_constraints": {
    "max_leverage": 1,
    "requires_stoploss": true,
    "max_strategy_drawdown_pct": 10,
    "max_daily_loss_pct": 2,
    "cooldown_after_loss_count": 3
  },
  "execution_constraints": {
    "order_type_allowed": ["limit", "market"],
    "max_slippage_bps": 20,
    "min_liquidity_score": 50,
    "position_sizing_mode": "external_execution_system_only"
  },
  "human_approval": {
    "required": true,
    "approved_by": null,
    "approved_at": null
  }
}
```

## Key Interfaces

### 1. Candidate Export API

Purpose: let the execution system pull approved research candidates.

```http
GET /api/deployment-candidates?status=DEPLOYMENT_CANDIDATE
GET /api/deployment-candidates/{candidate_id}
```

Rules:

```text
read-only from execution system perspective
no exchange secrets
no position sizing authority
include evidence references and risk constraints
```

### 2. Execution Feedback API

Purpose: let the execution system send paper/live outcomes back into research.

```http
POST /api/execution-feedback
```

Recommended payload:

```json
{
  "candidate_id": "deploy_001",
  "strategy_id": "strategy_001",
  "environment": "paper",
  "period_start": "2026-05-13T00:00:00Z",
  "period_end": "2026-05-20T00:00:00Z",
  "orders": 42,
  "fills": 39,
  "realized_pnl_pct": 1.8,
  "max_drawdown_pct": 2.4,
  "slippage_bps_avg": 7.2,
  "rejections": 1,
  "risk_events": [
    "cooldown_triggered"
  ]
}
```

Research usage:

```text
compare paper/live behavior with backtest
detect execution decay
identify slippage or liquidity mismatch
create failure review cases
update watchlist or retirement decisions
```

### 3. Risk Policy Export

Purpose: expose research-side constraints to the execution system.

```http
GET /api/deployment-candidates/{candidate_id}/risk-policy
```

The execution system may enforce stricter rules, but may not loosen research-side constraints without a new human approval.

### 4. Context Snapshot API

Purpose: allow execution to query research context without letting research place orders.

```http
GET /api/market-context/latest?symbol=BTC/USDT&timeframe=5m
```

Current-stage behavior:

```text
context is advisory
permission score is research-only
execution system decides whether to consume it
```

### 5. Audit Trail API

Purpose: make every deployment candidate traceable.

```http
GET /api/deployment-candidates/{candidate_id}/audit-trail
```

Must include:

```text
original thesis
strategy code hash
risk audit result
backtest result
validation result
Monte Carlo result
review cases
human approvals
execution feedback
retirement decisions
```

## Execution System Requirements

Any downstream order system must own:

```text
exchange credentials
account and portfolio state
position sizing
order placement
fill reconciliation
live risk limits
kill switch
capital allocation
operator approval
incident response
```

It must not rely on QuantOdyssey to:

```text
decide account-level exposure
increase leverage
override stoploss
ignore blocked symbols
skip cooldowns
hide execution failures
```

## Research Feedback Loop

Execution results must flow back into Harness.

```text
ExecutionFeedback
-> Evidence Builder
-> Paper/Live vs Backtest Comparison
-> Failure Summary
-> Watchlist / Retirement / New Research Task
```

Typical Harness tasks generated from execution feedback:

```text
slippage stress test
liquidity bucket review
paper vs backtest divergence review
symbol-specific decay review
cooldown rule review
retirement criteria review
```

## Security Boundary

QuantOdyssey should not store:

```text
exchange API keys
withdrawal credentials
private keys
production account secrets
```

If integration requires authentication, use service tokens scoped only to:

```text
read deployment candidates
write execution feedback
read market context
read audit trail
```

## Minimum V1 Implementation

The first implementation should only add:

```text
DeploymentCandidate model
candidate export endpoint or JSON artifact
execution feedback model
feedback ingestion endpoint or JSON import
audit trail references
Harness task generation from feedback
```

Do not implement live order routing inside QuantOdyssey.

