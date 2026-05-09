
# prompt_contracts.md

# Prompt Contracts

本文定义各 Agent 调用 LLM 时的输入、输出和约束。

所有 LLM 调用必须：

- 使用结构化输入
- 输出可解析 JSON
- 保留 prompt / response 日志
- 不接收 secrets
- 不直接触发交易

---

# Global Rules

## Required Metadata

每次 LLM 调用必须记录：

```json
{
  "prompt_id": "prompt_001",
  "agent": "strategy_researcher",
  "model": "gpt-5",
  "temperature": 0.2,
  "signal_id": "signal_001",
  "strategy_id": "strategy_001",
  "created_at": "2026-05-09T00:00:00Z"
}
````

## Forbidden Content

Prompt 中不得包含：

```text
API keys
exchange secrets
wallet addresses private keys
database passwords
personal credentials
```

## Output Rule

LLM 输出必须满足：

```text
1. JSON 可解析
2. 字段符合 Pydantic model
3. 不包含 Markdown 包裹
4. 不包含额外解释文本
```

---

# Contract 1: Strategy Researcher

## Purpose

根据 MarketSignal 和历史案例生成候选 Freqtrade 策略。

## Input

```json
{
  "market_signal": {
    "signal_id": "signal_001",
    "exchange": "binance",
    "symbol": "BTC/USDT",
    "timeframe": "5m",
    "signal_type": "volume_spike",
    "rank_score": 82,
    "features": {
      "volume_zscore": 3.1,
      "price_change_pct": 0.024
    },
    "hypothesis": "volume spike may indicate short-term continuation"
  },
  "retrieved_cases": [
    {
      "case_id": "case_001",
      "pattern": "volume spike worked better with trend filter",
      "avoid_conditions": ["ADX < 15"],
      "reusable_lessons": ["add trend confirmation"]
    }
  ],
  "constraints": {
    "framework": "freqtrade",
    "timeframe": "5m",
    "must_include_stoploss": true,
    "max_leverage": 1,
    "allow_short": false
  }
}
```

## Required Output

```json
{
  "strategy_name": "VolumeSpikeTrendV1",
  "strategy_code": "class VolumeSpikeTrendV1(IStrategy): ...",
  "manifest": {
    "strategy_id": "strategy_001",
    "signal_id": "signal_001",
    "name": "VolumeSpikeTrendV1",
    "timeframe": "5m",
    "symbols": ["BTC/USDT"],
    "assumptions": [
      "Volume spike indicates short-term momentum"
    ],
    "failure_modes": [
      "Fails during low-liquidity fake breakouts"
    ]
  }
}
```

## Hard Constraints

Researcher 必须：

```text
生成 Freqtrade IStrategy
包含 stoploss
包含 timeframe
包含 populate_indicators
包含 populate_entry_trend
包含 populate_exit_trend
不得包含实盘 API 调用
不得读取环境变量
不得执行文件系统操作
不得动态下载远程代码
```

---

# Contract 2: Risk Auditor

## Purpose

审查 strategy.py 是否存在明显风险。

## Input

```json
{
  "strategy_id": "strategy_001",
  "strategy_name": "VolumeSpikeTrendV1",
  "strategy_code": "class VolumeSpikeTrendV1(IStrategy): ...",
  "manifest": {
    "timeframe": "5m",
    "symbols": ["BTC/USDT"],
    "assumptions": [],
    "failure_modes": []
  },
  "risk_limits": {
    "max_leverage": 1,
    "require_stoploss": true,
    "allow_dca": false,
    "allow_short": false
  }
}
```

## Required Output

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

## Hard Constraints

Risk Auditor 必须拒绝：

```text
missing stoploss
martingale
unlimited DCA
leverage > max_leverage
lookahead bias
future leakage
external network calls
dynamic code execution
direct exchange trading calls
```

---

# Contract 3: Reviewer Agent

## Purpose

根据 MarketSignal、RiskAuditResult、BacktestReport 和 trades.json 生成复盘案例。

## Input

```json
{
  "market_signal": {
    "signal_id": "signal_001",
    "symbol": "BTC/USDT",
    "signal_type": "volume_spike",
    "rank_score": 82,
    "features": {
      "volume_zscore": 3.1
    }
  },
  "strategy_manifest": {
    "strategy_id": "strategy_001",
    "name": "VolumeSpikeTrendV1",
    "assumptions": [
      "Volume spike indicates continuation"
    ],
    "failure_modes": [
      "Fake breakout"
    ]
  },
  "risk_audit_result": {
    "approved": true,
    "findings": []
  },
  "backtest_report": {
    "profit_factor": 0.91,
    "max_drawdown": -0.19,
    "trades": 74,
    "win_rate": 0.43,
    "status": "failed"
  },
  "trade_summary": {
    "largest_loss_reason": "failed breakout",
    "worst_market_condition": "choppy range"
  }
}
```

## Required Output

```json
{
  "case_id": "case_001",
  "strategy_id": "strategy_001",
  "signal_id": "signal_001",
  "result": "failed",
  "pattern": "Volume spike continuation failed in choppy range.",
  "failure_reason": "Breakouts lacked trend confirmation.",
  "avoid_conditions": [
    "ADX < 15",
    "low liquidity session"
  ],
  "reusable_lessons": [
    "Add trend filter before entering volume spike continuation trades.",
    "Avoid trading volume spike alone during range-bound markets."
  ]
}
```

## Hard Constraints

Reviewer 不得：

```text
修改策略代码
审批策略上线
建议实盘部署
生成交易指令
```

---

# Contract 4: PM / Orchestrator Summary

## Purpose

将 workflow 状态压缩为可通知人类的摘要。

## Input

```json
{
  "workflow_run_id": "run_001",
  "signal_id": "signal_001",
  "strategy_id": "strategy_001",
  "state": "BACKTEST_PASSED",
  "backtest_report": {
    "profit_factor": 1.34,
    "max_drawdown": -0.09,
    "trades": 116,
    "win_rate": 0.54
  },
  "review_case": {
    "pattern": "Trend-filtered volume spike worked in high momentum conditions.",
    "reusable_lessons": [
      "Use trend filter",
      "Avoid low liquidity periods"
    ]
  }
}
```

## Required Output

```json
{
  "title": "Strategy backtest passed",
  "summary": "VolumeSpikeTrendV1 passed MVP criteria with profit_factor 1.34 and max_drawdown -0.09.",
  "decision_required": true,
  "decision_options": [
    "approve_paper_trading",
    "reject",
    "request_manual_review"
  ],
  "risks": [
    "Only validated on historical data",
    "No live execution evidence"
  ]
}
```

## Hard Constraints

PM Summary 不得：

```text
自动批准 paper trading
自动批准 live trading
隐藏风险
省略 Risk Auditor 结果
```

---

# Prompt Templates

## Strategy Researcher Template

```text
You are Strategy Researcher for Quant Agent Platform.

Task:
Generate one candidate Freqtrade strategy from the provided MarketSignal and retrieved cases.

Rules:
- Output JSON only.
- Generate valid Python code for a Freqtrade IStrategy.
- Include stoploss.
- Include timeframe.
- Include populate_indicators.
- Include populate_entry_trend.
- Include populate_exit_trend.
- Do not include live trading code.
- Do not access environment variables.
- Do not use external network calls.
- Do not use dynamic code execution.

Input:
{{input_json}}

Output schema:
{{output_schema}}
```

---

## Risk Auditor Template

```text
You are Risk Auditor for Quant Agent Platform.

Task:
Review the provided Freqtrade strategy code for safety violations.

Rules:
- Output JSON only.
- Approve only if all required checks pass.
- Reject missing stoploss.
- Reject martingale.
- Reject unlimited DCA.
- Reject excessive leverage.
- Reject lookahead bias.
- Reject external network calls.
- Reject dynamic code execution.
- Do not modify strategy code.

Input:
{{input_json}}

Output schema:
{{output_schema}}
```

---

## Reviewer Template

```text
You are Reviewer Agent for Quant Agent Platform.

Task:
Convert the strategy result into a reusable ReviewCase.

Rules:
- Output JSON only.
- Focus on reusable lessons.
- Identify market conditions where the strategy failed or succeeded.
- Do not suggest live trading.
- Do not approve deployment.
- Do not modify strategy code.

Input:
{{input_json}}

Output schema:
{{output_schema}}
```

---

# Validation

Every LLM output must pass:

```text
json.loads()
Pydantic model validation
required field check
forbidden keyword scan
```

Invalid output must be marked:

```text
LLM_OUTPUT_INVALID
```

It must not proceed to the next workflow step.

---

# Versioning

Prompt files should be stored under:

```text
app/prompts/
```

Recommended structure:

```text
app/prompts/
├── strategy_researcher_v1.txt
├── risk_auditor_v1.txt
├── reviewer_v1.txt
└── pm_summary_v1.txt
```

Each prompt version must be referenced in logs:

```json
{
  "prompt_version": "strategy_researcher_v1",
  "prompt_hash": "sha256:..."
}
```

```
```
