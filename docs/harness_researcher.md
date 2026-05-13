# Harness Researcher

Harness 是 QuantOdyssey 的研究控制层。它更接近一个研究员，而不是交易员。

它不负责生成投资计划、不负责自动实盘、不负责调仓。它的目标是避免人类研究者成为瓶颈：自动整理失败案例、发现证据缺口、推动市场数据收集、生成下一批研究任务，让研究循环持续进行。

## Core Loop

```text
Research assets
-> Evidence Builder
-> Research Task Generator
-> Experiment Router
-> Result Analyzer
-> Finding Archive
-> Next Research Tasks
```

Harness 的核心产物不是订单，而是：

```text
research_tasks
experiment_runs
evidence_packs
research_findings
decision_records
watchlist_updates
data_requests
weekly_digest
```

## Responsibilities

Harness 应主动推动：

```text
失败案例总结
重复失败模式识别
市场数据缺口识别
事件频率统计
策略族优先级调整
watchlist 更新
baseline 测试
regime bucket 测试
Monte Carlo 与稳健性测试
参数敏感性测试
三方数据接入必要性判断
下一步研究任务生成
```

Harness 不应主动推动：

```text
实盘交易
资金分配
提高杠杆
绕过人工确认的大规模计算
绕过 Risk Auditor
使用未批准的外部数据源
把 LLM 生成内容直接当作 alpha 结论
```

Harness 可以在证据充分时生成 `DeploymentCandidate`，但它只是给外部下单系统和人工审批使用的研究包，不是订单、不包含仓位决策、不包含交易所密钥。

## Evidence Builder

Evidence Builder 是 Harness 的第一核心组件。它从现有研究资产中提取“下一步值得研究什么”。

输入：

```text
ResearchThesis
MarketSignal
StrategyManifest
BacktestReport
ValidationSuite
MonteCarloResult
ReviewCase
NegativeResult
EventEpisode
WatchlistEntry
MarketContext
```

输出：

```json
{
  "evidence_pack_id": "ep_001",
  "subject": "failed_breakout_punishment",
  "observations": [
    "event frequency is acceptable on BTC/USDT 5m",
    "profit factor is positive only during NORMAL regime",
    "false positives cluster during STRONG_TREND"
  ],
  "evidence_gaps": [
    "no orderbook data to confirm absorption",
    "no event-resampling Monte Carlo yet"
  ],
  "suggested_tasks": [
    "run regime bucket baseline comparison",
    "create watchlist for low-frequency symbols",
    "test naive event entry baseline"
  ],
  "severity": "medium",
  "opportunity": "high"
}
```

## Research Task Types

Harness 生成的任务应是可执行、可验证、可记录的原子研究任务。

推荐任务类型：

```text
event_frequency_scan
baseline_test
event_definition_test
regime_bucket_test
cross_symbol_test
walk_forward_test
out_of_sample_test
monte_carlo_test
parameter_sensitivity_test
data_sufficiency_review
external_data_need_review
failure_cluster_review
watchlist_review
strategy_family_priority_review
```

每个任务至少包含：

```json
{
  "task_id": "task_001",
  "task_type": "baseline_test",
  "subject_type": "strategy_family",
  "subject_id": "failed_breakout_punishment",
  "hypothesis": "failed breakout events outperform naive event entry during NORMAL regime",
  "required_data_level": "L0",
  "expected_output": "baseline comparison report",
  "approval_required": false,
  "priority": 78
}
```

## Autonomy Levels

Harness 可以自动运行低风险研究任务，但必须在人类确认后运行高开销或高复杂度任务。

### Auto-Run Allowed

```text
small event frequency scans
simple baseline tests
small regime bucket summaries
review case summarization
negative result clustering
watchlist updates
data sufficiency classification
small cross-symbol smoke tests
```

### Human Approval Required

```text
large Monte Carlo runs
large optimizer grids
new external paid data source
long-running cross-symbol batch
new strategy family introduction
paper promotion
capital-related decisions
```

## Failure Case Summarization

失败案例是平台最重要的资产之一。Harness 应把失败拆成可复用知识，而不是只记录“回测失败”。

失败总结维度：

```text
strategy_family
evaluation_type
event_definition
regime
symbol
timeframe
data_sufficiency_level
failure_pattern
likely_false_assumption
missing_data
baseline_comparison
reusable_lesson
next_task
```

示例：

```json
{
  "failure_pattern": "failed breakout shorts lose during strong trend acceptance",
  "likely_false_assumption": "returning inside range was treated as rejection, but trend acceptance remained strong",
  "reusable_lesson": "require trend exhaustion or lower trend_score before shorting failed upside breakouts",
  "next_task": "test failed breakout events bucketed by trend_score"
}
```

## Market Data Collection

Harness 应把数据收集当作研究任务，而不是默认引入所有数据源。

当研究发现以下问题时，才生成数据需求：

```text
existing OHLCV proxy cannot distinguish mechanism
funding or OI is required to verify crowding
liquidation data is required to verify forced flow
orderbook/trades are required to verify absorption
on-chain/wallet data is required to verify medium-term flow pressure
```

数据需求任务示例：

```json
{
  "task_type": "external_data_need_review",
  "data_source": "glassnode",
  "reason": "OHLCV cannot distinguish exchange inflow pressure from normal volatility",
  "linked_strategy_family": "event_overreaction_fade",
  "approval_required": true
}
```

## Optimizer Boundary

Harness 可以安排参数敏感性测试，但 optimizer 只用于验证稳健性，不用于自动改写策略逻辑。

允许：

```text
predeclared thresholds
predeclared windows
stop buffers
holding period limits
filter thresholds
signal weights
```

禁止：

```text
searching arbitrary rule trees
changing long/short direction
adding unapproved indicators
changing strategy family
optimizing only for best backtest profit
```

## Research Digest

Harness 应定期生成研究摘要，帮助人类快速判断下一步重点。

摘要应包含：

```text
top strategy families by opportunity frequency
top failed assumptions
new watchlist entries
research tasks completed
tasks waiting for approval
data gaps blocking progress
recommended next 3-5 research actions
```

## Design Principle

Harness 的最高目标：

```text
让研究循环不断前进，同时保持所有结论可解释、可追溯、可反驳。
```

当外部执行系统回传 paper/live feedback 时，Harness 应把它视为新的研究证据，生成失败总结、滑点/流动性审查、paper vs backtest divergence review、watchlist 更新或 retirement 任务。
