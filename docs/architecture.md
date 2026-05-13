# architecture.md

# System Architecture

Quant Agent Platform 是一个多 Agent 量化研究平台，用于把人类市场 thesis 转化为可执行实验、风险审查、回测验证和可复用研究资产。

系统目标不是自动实盘交易，而是自动化量化研究闭环。

当前研究规范见：

* [Product Vision](product_vision.md)
* [Research OS](research_os.md)
* [Evaluation Profiles](evaluation_profiles.md)
* [Harness Researcher](harness_researcher.md)
* [Execution Integration](execution_integration.md)

---

# Architecture Overview

```text
Market Data
   ↓
Market Context Engine
   ↓
Market Scout / Event Detector
   ↓
MarketSignal
   ↓
Research Harness
   ↓
Prefect Orchestrator
   ↓
Strategy Researcher
   ↓
Risk Auditor
   ↓
Backtest Specialist
   ↓
Reviewer Agent
   ↓
Research Asset Store / RAG Knowledge Base
   ↓
DeploymentCandidate Export
   ↓
External Execution System
````

n8n 作为外部协作层：

```text
n8n
├── Webhook
├── Human Approval
├── Notification
└── Prefect API Trigger
```

---

# Component Responsibilities

## 1. n8n

负责：

* 接收外部 Webhook
* 触发 Prefect Flow
* 人工审批
* 发送通知
* 展示流程状态

禁止：

* 生成策略
* 执行回测
* 修改策略代码
* 执行交易
* 绕过 Risk Auditor

---

## 2. Prefect Orchestrator

负责核心流程调度：

* 接收 MarketSignal
* 调用 Researcher
* 调用 Risk Auditor
* 调用 Backtester
* 调用 Reviewer
* 记录状态变化
* 处理失败与重试

Prefect 是 MVP 阶段的核心编排层。

## 2A. Research Harness

负责推动研究循环，而不是交易执行。

输入：

* thesis
* signals
* event episodes
* backtest reports
* validation results
* review cases
* negative results
* watchlist entries

输出：

* evidence packs
* research tasks
* experiment plans
* failure summaries
* data collection requests
* research digest

禁止：

* 自动生成投资计划
* 自动调仓
* 自动提高杠杆
* 绕过人工确认运行高开销实验
* 把 LLM 生成内容直接当作 alpha 结论

Harness 可以生成 DeploymentCandidate 研究包，但不能生成订单。DeploymentCandidate
是研究系统与外部下单系统之间的边界对象。

---

## 3. Market Scout

负责发现市场异动。

输入：

* OHLCV
* Funding rate
* Open interest
* Orderbook
* Liquidation data

输出：

* MarketSignal

不负责：

* 策略生成
* 回测
* 交易执行

## 3A. Market Context Engine

负责生成共享市场上下文。

第一版 regime：

* NORMAL
* STRONG_TREND
* CRASH
* CHAOS

输出：

* trend score
* fragility score
* volatility score
* liquidity score
* crash risk score
* data sufficiency level

现阶段 Permission Layer 只输出研究用风险评分，不自动禁用策略、不调整仓位、不生成投资计划。

---

## 4. Strategy Researcher

负责生成候选 Freqtrade 策略。

输入：

* MarketSignal
* RAG 历史案例
* 策略模板

输出：

* strategy.py
* StrategyManifest
* assumptions
* failure_modes

不负责：

* 风控审批
* 回测执行
* 实盘交易

---

## 5. Risk Auditor

负责策略静态风险审查。

检查：

* stoploss
* leverage
* martingale
* 无限加仓
* lookahead bias
* future leakage
* position sizing

输出：

* RiskAuditResult

Risk Auditor 拒绝后，策略不得进入回测。

---

## 6. Backtest Specialist

负责调用 Freqtrade 执行回测。

输入：

* 已通过 Risk Auditor 的 strategy.py
* historical market data

输出：

* BacktestReport
* trades.json

不负责：

* 修改策略
* 审批上线
* 执行实盘

---

## 7. Reviewer Agent

负责复盘策略表现。

输入：

* MarketSignal
* BacktestReport
* trades.json

输出：

* ReviewCase
* failure pattern
* reusable lessons

Reviewer 的结果写入 RAG Knowledge Base。

---

# Data Flow

```text
1. Market Scout 生成 MarketSignal
2. Prefect 接收 signal_id
3. Researcher 生成候选策略
4. Risk Auditor 执行静态审查
5. Backtester 执行 Freqtrade 回测
6. Reviewer 生成复盘案例
7. 案例写入 RAG
8. 后续 Researcher 检索历史案例
```

---

# State Machine

```text
NEW_SIGNAL
→ RESEARCH_REQUESTED
→ STRATEGY_GENERATED
→ RISK_AUDITING
→ RISK_APPROVED / RISK_REJECTED
→ BACKTEST_RUNNING
→ BACKTEST_PASSED / BACKTEST_FAILED
→ REVIEW_COMPLETED
→ HUMAN_REVIEW_REQUIRED
→ PAPER_TRADING_APPROVED
→ RETIRED
```

MVP 只实现：

```text
NEW_SIGNAL
→ STRATEGY_GENERATED
→ RISK_AUDITING
→ BACKTEST_RUNNING
→ REVIEW_COMPLETED
```

---

# Storage

## PostgreSQL

存储：

* signals
* strategies
* risk_audit_results
* backtest_reports
* workflow_states

## Vector Database

存储：

* successful cases
* failed cases
* market patterns
* strategy assumptions
* reusable lessons

## File Storage

存储：

* generated strategies
* Freqtrade results
* prompt logs
* review artifacts

---

# Runtime Boundaries

## n8n

外部协作层。

## Prefect

核心 workflow 层。

## Freqtrade

回测与纸交易执行层。

## External Execution System

真实下单系统必须独立于 QuantOdyssey。

负责：

* exchange credentials
* account state
* portfolio constraints
* position sizing
* order routing
* fills / positions
* live risk controls
* kill switch

QuantOdyssey 只输出 DeploymentCandidate、risk constraints、audit trail 和 market context
snapshot，并接收 execution feedback 作为后续研究资产。

## LLM Providers

策略研究与复盘分析层。

## Databases

状态、结果和知识存储层。

---

# Safety Boundaries

系统必须遵守：

* 不自动实盘交易
* 不自动提高杠杆
* 不绕过 Risk Auditor
* 不允许无 stoploss 策略
* 不允许无限加仓
* 不把 API secrets 写入日志或 RAG
* 不让 n8n 直接调用交易执行

---

# MVP Scope

MVP 包含：

* MarketSignal 数据模型
* Scout mock signal
* Researcher mock strategy generation
* Risk Auditor static checks
* Freqtrade backtest wrapper
* BacktestReport parser
* Reviewer case generation
* RAG write interface
* n8n approval workflow

MVP 不包含：

* live trading
* portfolio optimization
* multi-exchange execution
* advanced execution engine
* HFT
* autonomous capital allocation

---

# Final Principle

This platform is a quantitative research automation system.

It is not an autonomous trading bot.

```
```
