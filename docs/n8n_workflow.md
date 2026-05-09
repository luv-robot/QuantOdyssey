````markdown
# n8n_workflow.md

# n8n Workflow

n8n 仅负责：

- Webhook 入口
- 人工审批
- 通知
- 调用 Prefect API
- 展示流程状态

n8n 不负责：

- 生成策略
- 执行回测
- 修改策略代码
- 执行实盘交易
- 绕过 Risk Auditor

---

# Workflow 1: New Signal Intake

## Trigger

```text
Webhook: POST /signal
````

## Input

```json
{
  "signal_id": "signal_001",
  "symbol": "BTC/USDT",
  "signal_type": "volume_spike",
  "rank_score": 82
}
```

## Flow

```text
Webhook
  ↓
Validate JSON
  ↓
IF rank_score >= MIN_SIGNAL_RANK
  ├─ No  → Archive Signal
  └─ Yes → Call Prefect Research Flow
```

## Output

```json
{
  "status": "accepted",
  "signal_id": "signal_001"
}
```

---

# Workflow 2: Research Flow Trigger

## Trigger

From Workflow 1

## Action

```text
HTTP Request → Prefect API
```

## Payload

```json
{
  "flow_name": "research_flow",
  "signal_id": "signal_001"
}
```

## Flow

```text
Call Prefect Research Flow
  ↓
Wait / Poll Flow Status
  ↓
IF strategy_generated = true
  ├─ No  → Send Failure Notification
  └─ Yes → Continue
```

---

# Workflow 3: Risk Audit Result

## Trigger

Prefect callback or polling result

## Input

```json
{
  "strategy_id": "strategy_001",
  "approved": true,
  "findings": []
}
```

## Flow

```text
Receive RiskAuditResult
  ↓
IF approved = true
  ├─ No  → Send Rejection Notification
  └─ Yes → Call Prefect Backtest Flow
```

---

# Workflow 4: Backtest Result

## Trigger

Prefect callback or polling result

## Input

```json
{
  "strategy_id": "strategy_001",
  "profit_factor": 1.35,
  "max_drawdown": -0.11,
  "sharpe": 1.42,
  "status": "passed"
}
```

## Pass Criteria

```text
profit_factor >= 1.2
max_drawdown >= -0.15
trades >= 50
status = passed
```

## Flow

```text
Receive BacktestReport
  ↓
IF pass criteria met
  ├─ No  → Send Backtest Failed Notification
  └─ Yes → Human Approval
```

---

# Workflow 5: Human Approval

## Trigger

Backtest passed

## Approver Options

```text
Approve Paper Trading
Reject
Request Review
```

## Flow

```text
Human Approval
  ├─ Reject         → Mark Rejected
  ├─ Request Review → Send to Reviewer
  └─ Approve        → Call Promote to Paper Trading
```

---

# Workflow 6: Notification

## Channels

* Slack
* Feishu
* Email

## Events

```text
signal_accepted
strategy_generated
risk_rejected
backtest_failed
backtest_passed
human_approval_required
paper_trading_approved
workflow_failed
```

---

# Required Environment Variables

```env
N8N_WEBHOOK_SECRET=
PREFECT_API_URL=
PREFECT_API_KEY=
MIN_SIGNAL_RANK=70
SLACK_WEBHOOK_URL=
FEISHU_WEBHOOK_URL=
```

---

# Minimal Node List

```text
Webhook
Set
IF
HTTP Request
Wait
Respond to Webhook
Slack / Feishu
```

---

# Safety Rules

n8n must never:

* call Freqtrade directly
* edit strategy files
* approve live trading automatically
* change risk limits
* store API secrets in workflow nodes

```
```
