
# mvp_tasks.md

# MVP Task List

本文定义 Quant Agent Platform MVP 的开发任务清单。

目标：跑通最小闭环。

```text
MarketSignal
→ Strategy Generation
→ Risk Audit
→ Backtest
→ Review
→ RAG Storage
→ Human Approval
````

---

# Phase 0: Project Foundation

## Tasks

```text
MVP-0001 创建项目目录结构
MVP-0002 创建 README.md
MVP-0003 创建 AGENTS.md
MVP-0004 创建 docs/architecture.md
MVP-0005 创建 docs/workflow.md
MVP-0006 创建 docs/n8n_workflow.md
MVP-0007 创建 docs/api_spec.md
MVP-0008 创建 docs/prompt_contracts.md
MVP-0009 创建 .env.example
MVP-0010 创建 pyproject.toml
MVP-0011 创建基础 pytest 配置
MVP-0012 创建 docker-compose.yml
```

## Acceptance Criteria

```text
项目可以安装
pytest 可以运行
docs 目录完整
Codex 可根据文档继续开发
```

---

# Phase 1: Core Data Models

## Tasks

```text
MVP-0101 创建 app/models/signal.py
MVP-0102 创建 app/models/strategy.py
MVP-0103 创建 app/models/risk.py
MVP-0104 创建 app/models/backtest.py
MVP-0105 创建 app/models/review.py
MVP-0106 创建 app/models/workflow.py
MVP-0107 添加 Pydantic validation tests
MVP-0108 添加 JSON schema export 脚本
```

## Acceptance Criteria

```text
所有 Agent 输入输出均使用 Pydantic Model
非法 payload 会被拒绝
测试覆盖所有核心模型
```

---

# Phase 2: Storage Layer

## Tasks

```text
MVP-0201 创建 app/storage/postgres.py
MVP-0202 创建 SQLAlchemy models
MVP-0203 创建 signals 表
MVP-0204 创建 strategies 表
MVP-0205 创建 risk_audits 表
MVP-0206 创建 backtests 表
MVP-0207 创建 reviews 表
MVP-0208 创建 workflow_runs 表
MVP-0209 创建 app/storage/vector_store.py
MVP-0210 实现 ReviewCase 写入接口
MVP-0211 实现 ReviewCase 查询接口
```

## Acceptance Criteria

```text
MarketSignal 可写入数据库
BacktestReport 可写入数据库
ReviewCase 可写入向量库或 mock vector store
```

---

# Phase 3: Market Scout MVP

## Tasks

```text
MVP-0301 创建 app/services/scout/
MVP-0302 实现 mock_signal_generator.py
MVP-0303 实现 volume_spike mock signal
MVP-0304 实现 funding_oi_extreme mock signal
MVP-0305 实现 signal rank_score 过滤
MVP-0306 输出 MarketSignal JSON
MVP-0307 写入 storage
MVP-0308 创建 scout_flow.py
```

## Acceptance Criteria

```text
可生成 rank_score >= MIN_SIGNAL_RANK 的 MarketSignal
MarketSignal 可触发后续 workflow
```

---

# Phase 4: Strategy Researcher MVP

## Tasks

```text
MVP-0401 创建 app/services/researcher/
MVP-0402 创建 app/prompts/strategy_researcher_v1.txt
MVP-0403 实现 mock LLM response
MVP-0404 根据 MarketSignal 生成 Freqtrade strategy.py
MVP-0405 生成 StrategyManifest
MVP-0406 保存策略到 freqtrade_user_data/strategies/
MVP-0407 保存 prompt log
MVP-0408 保存 response log
MVP-0409 创建 research_flow.py
```

## Acceptance Criteria

```text
生成的 strategy.py 可被 Freqtrade 识别
StrategyManifest 可通过 Pydantic 校验
策略文件路径正确
```

---

# Phase 5: Risk Auditor MVP

## Tasks

```text
MVP-0501 创建 app/services/risk_auditor/
MVP-0502 实现 stoploss 检查
MVP-0503 实现 leverage 检查
MVP-0504 实现 martingale 关键词检查
MVP-0505 实现 unlimited DCA 检查
MVP-0506 实现 lookahead bias 关键词检查
MVP-0507 实现 external network call 检查
MVP-0508 实现 dynamic code execution 检查
MVP-0509 输出 RiskAuditResult
MVP-0510 创建 risk_audit_flow.py
```

## Acceptance Criteria

```text
无 stoploss 策略必须被拒绝
包含危险模式的策略必须被拒绝
未通过风控的策略不得进入 backtest
```

---

# Phase 6: Backtest MVP

## Tasks

```text
MVP-0601 创建 app/services/backtester/
MVP-0602 实现 freqtrade CLI wrapper
MVP-0603 实现 strategy name 解析
MVP-0604 实现 timerange 参数
MVP-0605 实现 backtest command builder
MVP-0606 执行 freqtrade backtesting
MVP-0607 解析 Freqtrade result JSON
MVP-0608 生成 BacktestReport
MVP-0609 保存 backtest result
MVP-0610 创建 backtest_flow.py
```

## Acceptance Criteria

```text
risk_approved 策略可执行一次回测
BacktestReport 包含 trades、win_rate、profit_factor、max_drawdown、total_return
回测失败时返回明确错误
```

---

# Phase 7: Reviewer MVP

## Tasks

```text
MVP-0701 创建 app/services/reviewer/
MVP-0702 创建 app/prompts/reviewer_v1.txt
MVP-0703 读取 MarketSignal
MVP-0704 读取 StrategyManifest
MVP-0705 读取 RiskAuditResult
MVP-0706 读取 BacktestReport
MVP-0707 读取 trades summary
MVP-0708 生成 ReviewCase
MVP-0709 写入 vector store
MVP-0710 创建 review_flow.py
```

## Acceptance Criteria

```text
每次 risk rejection 或 backtest 完成后都生成 ReviewCase
ReviewCase 可被后续 Researcher 查询
失败原因和 reusable_lessons 不为空
```

---

# Phase 8: Prefect End-to-End Flow

## Tasks

```text
MVP-0801 创建 app/flows/main_mvp_flow.py
MVP-0802 串联 scout_flow
MVP-0803 串联 research_flow
MVP-0804 串联 risk_audit_flow
MVP-0805 串联 backtest_flow
MVP-0806 串联 review_flow
MVP-0807 实现 workflow state update
MVP-0808 实现 retry policy
MVP-0809 实现 error handling
MVP-0810 实现 workflow run logging
```

## Acceptance Criteria

```text
输入一个 MarketSignal 后，系统可自动完成全流程
任一阶段失败时，workflow state 正确更新
Risk rejected 不进入 backtest
Backtest completed 后进入 review
```

---

# Phase 9: API MVP

## Tasks

```text
MVP-0901 创建 app/api/main.py
MVP-0902 实现 Bearer Token auth
MVP-0903 实现 POST /signals
MVP-0904 实现 GET /workflows/{workflow_run_id}
MVP-0905 实现 POST /strategies
MVP-0906 实现 POST /risk-audits
MVP-0907 实现 POST /backtests
MVP-0908 实现 POST /reviews
MVP-0909 实现 POST /approvals
MVP-0910 添加 API tests
```

## Acceptance Criteria

```text
n8n 可通过 API 提交 MarketSignal
n8n 可查询 workflow 状态
n8n 可提交人工审批结果
所有 API 均需要认证
```

---

# Phase 10: n8n Integration

## Tasks

```text
MVP-1001 创建 n8n/workflows/mvp_signal_workflow.json
MVP-1002 创建 Webhook: POST /signal
MVP-1003 添加 JSON validation node
MVP-1004 添加 rank_score 判断
MVP-1005 添加 HTTP Request 调用 POST /signals
MVP-1006 添加 workflow status polling
MVP-1007 添加 backtest_passed 判断
MVP-1008 添加 human approval step
MVP-1009 添加 Slack / Feishu notification
MVP-1010 添加 error notification
```

## Acceptance Criteria

```text
n8n 可接收 signal webhook
n8n 可触发后端 MVP workflow
backtest passed 后要求人工审批
n8n 不直接调用 Freqtrade
n8n 不直接修改策略文件
```

---

# Phase 11: Testing

## Tasks

```text
MVP-1101 添加 models tests
MVP-1102 添加 scout tests
MVP-1103 添加 researcher tests
MVP-1104 添加 risk auditor tests
MVP-1105 添加 backtester tests
MVP-1106 添加 reviewer tests
MVP-1107 添加 API tests
MVP-1108 添加 end-to-end mock workflow test
MVP-1109 添加 risk rejection test
MVP-1110 添加 invalid payload test
```

## Acceptance Criteria

```text
pytest 全部通过
核心模型有测试
风险拦截有测试
E2E mock flow 可运行
```

---

# Phase 12: Documentation Finalization

## Tasks

```text
MVP-1201 更新 README.md
MVP-1202 更新 AGENTS.md
MVP-1203 更新 docs/architecture.md
MVP-1204 更新 docs/workflow.md
MVP-1205 更新 docs/api_spec.md
MVP-1206 更新 docs/prompt_contracts.md
MVP-1207 更新 docs/n8n_workflow.md
MVP-1208 添加 docs/deployment.md
MVP-1209 添加 docs/security_policy.md
MVP-1210 添加 docs/mvp_roadmap.md
```

## Acceptance Criteria

```text
新开发者可根据文档启动项目
Codex 可根据文档继续开发
所有核心模块有对应说明
```

---

# MVP Completion Criteria

MVP 完成必须满足：

```text
1. 输入一个 MarketSignal
2. 系统生成一个 Freqtrade strategy.py
3. Risk Auditor 完成静态风险审查
4. 风控拒绝时流程停止并生成 ReviewCase
5. 风控通过时进入 Backtest
6. Backtester 输出 BacktestReport
7. Reviewer 输出 ReviewCase
8. ReviewCase 写入 RAG / vector store
9. n8n 可触发流程并处理人工审批
10. 所有核心流程有日志和状态记录
```

---

# Development Order

推荐开发顺序：

```text
1. Phase 0: Project Foundation
2. Phase 1: Core Data Models
3. Phase 3: Market Scout MVP
4. Phase 4: Strategy Researcher MVP
5. Phase 5: Risk Auditor MVP
6. Phase 6: Backtest MVP
7. Phase 7: Reviewer MVP
8. Phase 8: Prefect End-to-End Flow
9. Phase 9: API MVP
10. Phase 10: n8n Integration
11. Phase 11: Testing
12. Phase 12: Documentation Finalization
```

Storage Layer 可在 Phase 3 后逐步补全。

---

# Do Not Implement In MVP

```text
Live trading
Auto capital allocation
Auto leverage adjustment
Multi-exchange execution
Portfolio optimization
HFT
Reinforcement learning
Complex frontend
```

```
```
