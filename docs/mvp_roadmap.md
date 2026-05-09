
# MVP Roadmap

# Goal

MVP 目标是跑通最小自动化研究闭环：

```text
MarketSignal
→ Strategy Generation
→ Risk Audit
→ Backtest
→ Review
→ RAG Case Storage
````

MVP 不追求实盘盈利，只验证系统是否能持续产生、筛选、复盘候选策略。

---

# MVP Scope

## Included

* MarketSignal 数据模型
* Mock / 简化版 Market Scout
* Strategy Researcher
* Risk Auditor
* Freqtrade Backtest Wrapper
* BacktestReport Parser
* Reviewer Agent
* RAG 写入接口
* Prefect Flow
* n8n Webhook / Approval / Notification

## Excluded

* 实盘交易
* 自动调仓
* 自动提高杠杆
* 组合优化
* 多交易所执行
* 高频交易
* 强化学习
* 复杂前端

---

# Phase 0: Project Foundation

## Objective

建立项目骨架和统一开发规范。

## Tasks

```text
1. 创建项目目录
2. 添加 README.md
3. 添加 AGENTS.md
4. 添加 docs/architecture.md
5. 添加 docs/n8n_workflow.md
6. 添加 pyproject.toml
7. 添加 .env.example
8. 添加基础 pytest 配置
```

## Deliverables

```text
项目可安装
测试可运行
文档结构清晰
Codex 可接手开发
```

---

# Phase 1: Data Models

## Objective

定义 Agent 之间的通信契约。

## Tasks

```text
1. 创建 MarketSignal model
2. 创建 StrategyManifest model
3. 创建 RiskAuditResult model
4. 创建 BacktestReport model
5. 创建 ReviewCase model
6. 添加 schema validation tests
```

## Deliverables

```text
app/models/signal.py
app/models/strategy.py
app/models/risk.py
app/models/backtest.py
app/models/review.py
```

## Acceptance Criteria

```text
所有 Agent 输入输出均可通过 Pydantic 校验
非法 payload 会被拒绝
```

---

# Phase 2: Market Scout MVP

## Objective

生成可测试的市场信号。

## Tasks

```text
1. 实现 mock signal generator
2. 实现 volume_spike 示例信号
3. 实现 funding_oi_extreme 示例信号
4. 输出 MarketSignal JSON
5. 写入 Postgres 或本地 JSON 文件
```

## Deliverables

```text
app/services/scout/
app/flows/scout_flow.py
```

## Acceptance Criteria

```text
能够生成 rank_score >= 70 的 MarketSignal
能够触发后续 Research Flow
```

---

# Phase 3: Strategy Researcher MVP

## Objective

根据 MarketSignal 生成候选 Freqtrade 策略。

## Tasks

```text
1. 接收 MarketSignal
2. 使用固定 prompt 或 mock LLM response
3. 生成 Freqtrade strategy.py
4. 生成 StrategyManifest
5. 保存策略到 freqtrade_user_data/strategies/
6. 记录 prompt 和 response
```

## Deliverables

```text
app/services/researcher/
app/flows/research_flow.py
freqtrade_user_data/strategies/
```

## Acceptance Criteria

```text
生成的策略文件可被 Freqtrade 加载
StrategyManifest 可通过 Pydantic 校验
```

---

# Phase 4: Risk Auditor MVP

## Objective

在回测前拦截明显危险策略。

## Tasks

```text
1. 静态扫描 strategy.py
2. 检查 stoploss
3. 检查 leverage
4. 检查 martingale / 无限加仓关键词
5. 检查未来函数嫌疑
6. 输出 RiskAuditResult
```

## Deliverables

```text
app/services/risk_auditor/
app/models/risk.py
```

## Acceptance Criteria

```text
无 stoploss 策略必须被拒绝
高风险策略不得进入 Backtest Flow
```

---

# Phase 5: Backtest MVP

## Objective

封装 Freqtrade 回测流程。

## Tasks

```text
1. 创建 freqtrade CLI wrapper
2. 自动传入 strategy name
3. 执行 backtesting
4. 解析回测结果
5. 生成 BacktestReport
6. 保存结果
```

## Deliverables

```text
app/services/backtester/
app/flows/backtest_flow.py
freqtrade_user_data/backtest_results/
```

## Acceptance Criteria

```text
已通过 Risk Auditor 的策略可以完成一次回测
BacktestReport 包含 profit_factor、max_drawdown、trades、win_rate
```

---

# Phase 6: Reviewer MVP

## Objective

将回测结果转化为可复用经验。

## Tasks

```text
1. 读取 MarketSignal
2. 读取 BacktestReport
3. 读取 trades.json
4. 生成 ReviewCase
5. 提取成功/失败模式
6. 写入 RAG 接口
```

## Deliverables

```text
app/services/reviewer/
app/flows/review_flow.py
app/storage/vector_store.py
```

## Acceptance Criteria

```text
每次回测后都能生成 ReviewCase
失败原因可被后续 Researcher 检索
```

---

# Phase 7: Prefect End-to-End Flow

## Objective

串联完整 MVP 流程。

## Flow

```text
scout_flow
→ research_flow
→ risk_audit_flow
→ backtest_flow
→ review_flow
```

## Tasks

```text
1. 创建 main_mvp_flow.py
2. 串联所有 Agent
3. 添加状态记录
4. 添加失败处理
5. 添加基础 retry
```

## Deliverables

```text
app/flows/main_mvp_flow.py
```

## Acceptance Criteria

```text
输入一个 MarketSignal
系统自动完成策略生成、风控、回测、复盘
```

---

# Phase 8: n8n Integration

## Objective

提供 Webhook、审批和通知入口。

## Tasks

```text
1. 创建 /signal Webhook
2. 校验 signal payload
3. 调用 Prefect API
4. 接收 BacktestReport
5. 发送 Slack / Feishu 通知
6. Backtest Passed 后进入人工审批
```

## Deliverables

```text
n8n/workflows/mvp_signal_workflow.json
docs/n8n_workflow.md
```

## Acceptance Criteria

```text
n8n 可以触发完整 MVP Flow
人工可以审批是否进入 paper trading
```

---

# MVP Completion Criteria

MVP 完成的判断标准：

```text
1. 输入 MarketSignal
2. 自动生成 Freqtrade 策略
3. Risk Auditor 能拦截危险策略
4. Backtester 能完成一次回测
5. Reviewer 能生成复盘案例
6. RAG 能保存案例
7. n8n 能触发流程并通知人工审批
8. 全流程有日志和状态记录
```

---

# Suggested Development Order

```text
1. Project Foundation
2. Pydantic Models
3. Mock Scout
4. Mock Researcher
5. Risk Auditor
6. Backtest Wrapper
7. Reviewer
8. Prefect End-to-End Flow
9. n8n Integration
10. Real Data Source
```

---

# Success Metric

MVP 成功不是策略赚钱，而是系统能稳定完成：

```text
发现假设
→ 生成策略
→ 风控拦截
→ 回测验证
→ 复盘沉淀
```

每一次失败都必须转化为可复用案例。

```
```
