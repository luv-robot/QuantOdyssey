
# api_spec.md

# API Specification

本文定义 Quant Agent Platform MVP 的内部 API 规范。

API 主要用于：

- n8n 调用 Prefect / 后端服务
- Agent 间状态查询
- 工作流状态回调
- 人工审批
- 结果查询

---

# Base URL

```text
http://localhost:8000/api/v1
````

生产环境通过环境变量配置：

```env
API_BASE_URL=
API_AUTH_TOKEN=
```

---

# Auth

所有 API 请求必须带 Bearer Token。

```http
Authorization: Bearer <API_AUTH_TOKEN>
Content-Type: application/json
```

禁止在 URL query 中传递 token。

---

# Common Response

## Success

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

## Error

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid payload"
  }
}
```

---

# Error Codes

```text
VALIDATION_ERROR
UNAUTHORIZED
NOT_FOUND
CONFLICT
WORKFLOW_FAILED
RISK_REJECTED
BACKTEST_FAILED
INTERNAL_ERROR
```

---

# 1. Submit Market Signal

## Endpoint

```http
POST /signals
```

## Purpose

提交新的市场信号，触发 MVP 工作流。

## Request

```json
{
  "signal_id": "signal_001",
  "created_at": "2026-05-09T00:00:00Z",
  "market": "crypto",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "timeframe": "5m",
  "signal_type": "volume_spike",
  "rank_score": 82,
  "features": {
    "volume_zscore": 3.1,
    "price_change_pct": 0.024
  },
  "hypothesis": "Volume spike may indicate short-term continuation.",
  "data_sources": ["binance"]
}
```

## Response

```json
{
  "success": true,
  "data": {
    "signal_id": "signal_001",
    "workflow_run_id": "run_001",
    "state": "NEW_SIGNAL"
  },
  "error": null
}
```

## Validation

Reject if:

```text
schema invalid
rank_score < MIN_SIGNAL_RANK
unsupported exchange
unsupported symbol
duplicate signal_id
```

---

# 2. Get Signal

## Endpoint

```http
GET /signals/{signal_id}
```

## Response

```json
{
  "success": true,
  "data": {
    "signal_id": "signal_001",
    "symbol": "BTC/USDT",
    "signal_type": "volume_spike",
    "rank_score": 82,
    "state": "STRATEGY_GENERATED"
  },
  "error": null
}
```

---

# 3. Start Research Flow

## Endpoint

```http
POST /workflows/research
```

## Purpose

手动触发 Strategy Researcher。

通常由 Prefect 或 n8n 调用。

## Request

```json
{
  "signal_id": "signal_001"
}
```

## Response

```json
{
  "success": true,
  "data": {
    "workflow_run_id": "run_research_001",
    "signal_id": "signal_001",
    "state": "RESEARCH_REQUESTED"
  },
  "error": null
}
```

---

# 4. Get Workflow Status

## Endpoint

```http
GET /workflows/{workflow_run_id}
```

## Response

```json
{
  "success": true,
  "data": {
    "workflow_run_id": "run_001",
    "signal_id": "signal_001",
    "strategy_id": "strategy_001",
    "state": "BACKTEST_PASSED",
    "started_at": "2026-05-09T00:00:00Z",
    "updated_at": "2026-05-09T00:10:00Z",
    "error": null
  },
  "error": null
}
```

---

# 5. Register Generated Strategy

## Endpoint

```http
POST /strategies
```

## Purpose

Strategy Researcher 生成策略后登记策略元数据。

## Request

```json
{
  "strategy_id": "strategy_001",
  "signal_id": "signal_001",
  "name": "VolumeSpikeTrendV1",
  "file_path": "freqtrade_user_data/strategies/VolumeSpikeTrendV1.py",
  "generated_at": "2026-05-09T00:05:00Z",
  "timeframe": "5m",
  "symbols": ["BTC/USDT"],
  "assumptions": [
    "Volume spike indicates short-term continuation."
  ],
  "failure_modes": [
    "Fails in low-liquidity fake breakouts."
  ],
  "status": "generated"
}
```

## Response

```json
{
  "success": true,
  "data": {
    "strategy_id": "strategy_001",
    "status": "generated"
  },
  "error": null
}
```

---

# 6. Get Strategy

## Endpoint

```http
GET /strategies/{strategy_id}
```

## Response

```json
{
  "success": true,
  "data": {
    "strategy_id": "strategy_001",
    "signal_id": "signal_001",
    "name": "VolumeSpikeTrendV1",
    "status": "risk_approved",
    "file_path": "freqtrade_user_data/strategies/VolumeSpikeTrendV1.py"
  },
  "error": null
}
```

---

# 7. Submit Risk Audit Result

## Endpoint

```http
POST /risk-audits
```

## Purpose

Risk Auditor 提交审查结果。

## Request

```json
{
  "strategy_id": "strategy_001",
  "approved": false,
  "findings": [
    {
      "rule_id": "STOPLOSS_REQUIRED",
      "severity": "high",
      "message": "Strategy does not define stoploss."
    }
  ]
}
```

## Response

```json
{
  "success": true,
  "data": {
    "strategy_id": "strategy_001",
    "approved": false,
    "state": "RISK_REJECTED"
  },
  "error": null
}
```

## Rule

If `approved = false`:

```text
strategy must not enter backtest
workflow state becomes RISK_REJECTED
review case should still be created
```

---

# 8. Start Backtest

## Endpoint

```http
POST /workflows/backtest
```

## Purpose

触发已通过风控的策略回测。

## Request

```json
{
  "strategy_id": "strategy_001",
  "timerange": "20240101-20260501"
}
```

## Response

```json
{
  "success": true,
  "data": {
    "workflow_run_id": "run_backtest_001",
    "strategy_id": "strategy_001",
    "state": "BACKTEST_RUNNING"
  },
  "error": null
}
```

## Validation

Reject if:

```text
strategy not found
strategy not risk_approved
strategy file missing
timerange invalid
```

---

# 9. Submit Backtest Report

## Endpoint

```http
POST /backtests
```

## Purpose

Backtest Specialist 提交回测结果。

## Request

```json
{
  "strategy_id": "strategy_001",
  "timerange": "20240101-20260501",
  "trades": 116,
  "win_rate": 0.54,
  "profit_factor": 1.34,
  "sharpe": 1.42,
  "max_drawdown": -0.09,
  "total_return": 0.18,
  "status": "passed"
}
```

## Response

```json
{
  "success": true,
  "data": {
    "strategy_id": "strategy_001",
    "backtest_id": "backtest_001",
    "state": "BACKTEST_PASSED"
  },
  "error": null
}
```

---

# 10. Submit Review Case

## Endpoint

```http
POST /reviews
```

## Purpose

Reviewer Agent 提交复盘案例。

## Request

```json
{
  "case_id": "case_001",
  "strategy_id": "strategy_001",
  "signal_id": "signal_001",
  "result": "passed",
  "pattern": "Volume spike worked better with trend confirmation.",
  "failure_reason": null,
  "avoid_conditions": [
    "ADX < 15"
  ],
  "reusable_lessons": [
    "Add trend confirmation before entering volume spike trades."
  ]
}
```

## Response

```json
{
  "success": true,
  "data": {
    "case_id": "case_001",
    "stored": true,
    "state": "REVIEW_COMPLETED"
  },
  "error": null
}
```

---

# 11. Query Review Cases

## Endpoint

```http
GET /reviews
```

## Query Parameters

```text
signal_type
symbol
result
limit
```

## Example

```http
GET /reviews?signal_type=volume_spike&result=failed&limit=5
```

## Response

```json
{
  "success": true,
  "data": [
    {
      "case_id": "case_001",
      "pattern": "Volume spike failed in choppy range.",
      "avoid_conditions": ["ADX < 15"],
      "reusable_lessons": ["Add trend filter."]
    }
  ],
  "error": null
}
```

---

# 12. Human Approval

## Endpoint

```http
POST /approvals
```

## Purpose

n8n 提交人工审批结果。

## Request

```json
{
  "workflow_run_id": "run_001",
  "strategy_id": "strategy_001",
  "decision": "approve_paper_trading",
  "reviewer": "human_operator",
  "comment": "Approved for paper trading only."
}
```

## Allowed Decisions

```text
approve_paper_trading
reject
request_manual_review
```

## Response

```json
{
  "success": true,
  "data": {
    "strategy_id": "strategy_001",
    "decision": "approve_paper_trading",
    "state": "PAPER_TRADING_APPROVED"
  },
  "error": null
}
```

## Rule

Human approval may approve paper trading only.

Live trading is outside MVP scope.

---

# 13. Notification Callback

## Endpoint

```http
POST /callbacks/n8n
```

## Purpose

后端向 n8n 推送流程事件。

## Request

```json
{
  "event": "backtest_passed",
  "workflow_run_id": "run_001",
  "signal_id": "signal_001",
  "strategy_id": "strategy_001",
  "summary": "Strategy passed backtest criteria.",
  "requires_approval": true
}
```

## Response

```json
{
  "success": true,
  "data": {
    "received": true
  },
  "error": null
}
```

---

# State Enum

```text
NEW_SIGNAL
SIGNAL_VALIDATED
RESEARCH_REQUESTED
STRATEGY_GENERATED
RISK_AUDITING
RISK_APPROVED
RISK_REJECTED
BACKTEST_RUNNING
BACKTEST_PASSED
BACKTEST_FAILED
REVIEW_COMPLETED
HUMAN_REVIEW_REQUIRED
PAPER_TRADING_APPROVED
REJECTED
FAILED
```

---

# Signal Type Enum

```text
volume_spike
funding_oi_extreme
orderbook_imbalance
liquidation_cluster
```

---

# Strategy Status Enum

```text
generated
risk_rejected
risk_approved
backtest_running
backtest_failed
backtest_passed
review_completed
paper_trading
retired
```

---

# Backtest Status Enum

```text
passed
failed
error
```

---

# Approval Decision Enum

```text
approve_paper_trading
reject
request_manual_review
```

---

# API Safety Rules

API must never:

```text
accept live trading approval in MVP
accept leverage increase request
accept direct order execution request
start backtest before risk approval
store secrets in request body
return raw API keys
allow unauthenticated requests
```

---

# Minimal Implementation Files

```text
app/api/main.py
app/api/routes/signals.py
app/api/routes/workflows.py
app/api/routes/strategies.py
app/api/routes/risk_audits.py
app/api/routes/backtests.py
app/api/routes/reviews.py
app/api/routes/approvals.py
app/api/schemas.py
app/api/auth.py
```

---

# MVP Required Endpoints

MVP 必须实现：

```text
POST /signals
GET /workflows/{workflow_run_id}
POST /strategies
POST /risk-audits
POST /backtests
POST /reviews
POST /approvals
```

其余接口可后续补充。

```
```
