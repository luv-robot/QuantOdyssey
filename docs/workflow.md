
# workflow.md

# Workflow

本文定义 Quant Agent Platform MVP 的核心执行流程。

---

# Scope

本流程覆盖：

```text
MarketSignal
→ Research
→ Risk Audit
→ Backtest
→ Review
→ RAG Storage
````

不覆盖：

```text
Live Trading
Portfolio Management
Capital Allocation
Leverage Adjustment
```

---

# Workflow Overview

```text
1. Market Scout 生成 MarketSignal
2. Prefect 接收并创建 Workflow Run
3. Strategy Researcher 生成候选策略
4. Risk Auditor 执行静态风控审查
5. Backtest Specialist 执行 Freqtrade 回测
6. Reviewer Agent 生成复盘案例
7. ReviewCase 写入 RAG Knowledge Base
8. n8n 发送通知并处理人工审批
```

---

# Main Flow

```text
START
  ↓
Receive MarketSignal
  ↓
Validate Signal
  ↓
Generate Strategy
  ↓
Run Risk Audit
  ↓
IF risk_approved = false
  ├─ Write ReviewCase
  └─ END
  ↓
Run Backtest
  ↓
Parse BacktestReport
  ↓
Generate ReviewCase
  ↓
Store ReviewCase
  ↓
IF backtest_passed = true
  ├─ Notify Human Approval
  └─ END
  ↓
END
```

---

# State Transitions

```text
NEW_SIGNAL
→ SIGNAL_VALIDATED
→ STRATEGY_GENERATED
→ RISK_AUDITING
→ RISK_REJECTED / RISK_APPROVED
→ BACKTEST_RUNNING
→ BACKTEST_FAILED / BACKTEST_PASSED
→ REVIEW_COMPLETED
→ HUMAN_REVIEW_REQUIRED
```

---

# Step 1: Receive MarketSignal

## Input

```json
{
  "signal_id": "signal_001",
  "symbol": "BTC/USDT",
  "signal_type": "volume_spike",
  "rank_score": 82
}
```

## Validation

Required:

```text
signal_id
symbol
signal_type
rank_score
features
created_at
```

Reject if:

```text
rank_score < MIN_SIGNAL_RANK
schema invalid
symbol unsupported
```

## Output State

```text
SIGNAL_VALIDATED
```

---

# Step 2: Generate Strategy

## Owner

```text
Strategy Researcher
```

## Input

```text
MarketSignal
Relevant ReviewCases from RAG
Strategy Templates
```

## Output

```text
strategy.py
StrategyManifest
assumptions
failure_modes
```

## Output State

```text
STRATEGY_GENERATED
```

---

# Step 3: Risk Audit

## Owner

```text
Risk Auditor
```

## Input

```text
strategy.py
StrategyManifest
```

## Required Checks

```text
stoploss exists
leverage within limit
no martingale
no unlimited DCA
no lookahead bias
no future leakage
position sizing constrained
```

## Branch

```text
approved = true  → RISK_APPROVED
approved = false → RISK_REJECTED
```

Rejected strategies do not enter backtest.

---

# Step 4: Backtest

## Owner

```text
Backtest Specialist
```

## Input

```text
approved strategy.py
Freqtrade config
Historical market data
```

## Command

```bash
freqtrade backtesting \
  --strategy <StrategyName> \
  --config configs/freqtrade_config.json \
  --userdir freqtrade_user_data
```

## Output

```text
BacktestReport
trades.json
```

## Pass Criteria

```text
profit_factor >= 1.2
max_drawdown >= -0.15
trades >= 50
```

## Branch

```text
criteria met     → BACKTEST_PASSED
criteria not met → BACKTEST_FAILED
```

---

# Step 5: Review

## Owner

```text
Reviewer Agent
```

## Input

```text
MarketSignal
StrategyManifest
RiskAuditResult
BacktestReport
trades.json
```

## Output

```text
ReviewCase
```

## Required Fields

```text
case_id
strategy_id
signal_id
result
pattern
failure_reason
avoid_conditions
reusable_lessons
```

## Output State

```text
REVIEW_COMPLETED
```

---

# Step 6: RAG Storage

## Owner

```text
Reviewer Agent
```

## Input

```text
ReviewCase
```

## Storage

```text
Vector DB
PostgreSQL metadata table
```

## Stored Content

```text
market condition
strategy assumptions
failure pattern
success pattern
avoid conditions
reusable lessons
```

---

# Step 7: Human Approval

## Trigger

```text
BACKTEST_PASSED
```

## Owner

```text
n8n
```

## Options

```text
Approve Paper Trading
Reject
Request Manual Review
```

## Rule

Human approval is required before paper trading.

Live trading is outside MVP scope.

---

# Error Handling

## Retryable

```text
LLM timeout
market data timeout
Prefect task failure
temporary database error
Freqtrade process timeout
```

## Non-Retryable

```text
invalid schema
risk audit rejected
missing stoploss
unsupported symbol
malformed strategy.py
```

---

# Logging

Each workflow step must log:

```text
workflow_run_id
signal_id
strategy_id
state
input_hash
output_hash
started_at
finished_at
error
```

---

# Safety Rules

The workflow must never:

```text
skip Risk Auditor
run backtest on rejected strategy
promote to paper trading automatically
execute live trades
change leverage automatically
store secrets in RAG
```

---

# MVP Completion Criteria

The workflow is complete when:

```text
1. MarketSignal is validated
2. strategy.py is generated
3. RiskAuditResult is produced
4. BacktestReport is produced
5. ReviewCase is produced
6. ReviewCase is stored
7. Human approval is requested after passed backtest
