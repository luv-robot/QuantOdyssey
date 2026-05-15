# Quant Agent Platform

Multi-Agent Quantitative Research & Strategy Discovery Platform

一个用于把人类市场假设转化为可验证策略资产，并自动完成实现、回测、风险审查与持续复盘学习的多 Agent 平台。

---

# Vision

本项目目标不是“自动生成交易代码”，而是建立一个：

> 可持续发现 alpha、自动淘汰劣质策略、积累失败经验、持续迭代进化的量化研究系统。

平台采用：

- Multi-Agent 协作架构
- Human-led thesis + Agent-assisted strategy implementation
- 自动化回测与风险审查
- 持续复盘学习闭环
- Human-in-the-loop 审批机制

---

# Core Architecture

```text
┌────────────────────┐
│      n8n UI         │
│ 审批 / 通知 / Webhook │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│   Prefect Flows     │
│ 核心调度 / 状态推进 │
└─────────┬──────────┘
          │
 ┌────────┼──────────────────────────┐
 ▼        ▼                          ▼
Scout  Researcher               Backtester
 │        │                          │
 ▼        ▼                          ▼
signal  strategy.py             report.json
 │        │                          │
 └────────▼───────────────┬──────────┘
          Risk Auditor     │
                 │         ▼
                 ▼      Reviewer
              approved    │
                          ▼
                   RAG Failure DB


System Goals

系统目标：

自动发现市场异动
把人类研究假设结构化为 ResearchThesis
基于 ResearchThesis 生成候选策略实现
自动进行静态风险审查
自动执行回测
自动执行 Monte Carlo backtesting，并在高开销运行前要求人工确认
自动分析失败原因
建立策略案例知识库
减少重复犯错
长期积累 alpha 研究能力
Non-Goals (MVP)

MVP 阶段不做：

高频交易 (HFT)
超低延迟系统
自动实盘交易
全自动资金管理
强化学习 Agent
高频 orderflow execution
复杂分布式集群
Tech Stack
Workflow / Orchestration
Prefect
n8n
Trading Engine
Freqtrade
LLM Providers
OpenAI GPT-5
Claude
DeepSeek
Database
PostgreSQL
Vector Database
Qdrant / Chroma
Market Data
Binance
Coinglass
Nansen
CCXT
Multi-Agent Design
1. Market Scout

负责发现市场异动。

功能：

Volume Spike Detection
Funding/OI Extreme Detection
Orderbook Imbalance
Liquidation Cluster Scan

输出：
{
  "signal_id": "signal_001",
  "symbol": "BTC/USDT",
  "signal_type": "volume_spike",
  "rank_score": 83
}

2. Human-Led Strategy Researcher

负责：

接收人类 ResearchThesis
检索历史成功/失败案例
调用 LLM/agent 完善实现细节
输出 Freqtrade Strategy
保留 thesis_id 追溯

输出：

strategy.py
strategy_manifest.json
assumptions.md
failure_modes.md

LLM 不负责“自动发明 alpha”。策略必须从人类可理解、可反驳的市场假设出发。
3. Risk Auditor

负责：

静态代码风险审查
检查危险策略模式
拦截高风险策略

禁止：

无限加仓
Martingale
无 stoploss
未来函数
超高杠杆
4. Backtest Specialist

负责：

执行 Freqtrade 回测
收集绩效指标
输出结构化结果

输出：

{
  "sharpe": 1.42,
  "max_drawdown": -0.11,
  "profit_factor": 1.37
}
5. Reviewer Agent

负责：

分析 trades.json
对比预测与结果
总结失败原因
更新 RAG 案例库

核心目标：

系统化积累失败经验。

Project Structure
quant-agent-platform/
├── README.md
├── pyproject.toml
├── docs/
├── app/
├── configs/
├── freqtrade_user_data/
├── tests/
├── n8n/
└── scripts/

详细结构：

app/
├── api/
├── flows/
├── models/
├── services/
├── storage/
└── utils/
Data Flow
Market Data
    ↓
Market Scout
    ↓
MarketSignal
    ↓
Research Flow
    ↓
Strategy Generation
    ↓
Risk Audit
    ↓
Backtest
    ↓
Review
    ↓
Vector Knowledge Base
State Machine
NEW_SIGNAL
→ RESEARCH_REQUESTED
→ STRATEGY_GENERATED
→ RISK_AUDITING
→ RISK_APPROVED / REJECTED
→ BACKTEST_RUNNING
→ BACKTEST_PASSED / FAILED
→ HUMAN_REVIEW
→ PAPER_TRADING
→ RETIRED

MVP 阶段仅实现：

NEW_SIGNAL
→ STRATEGY_GENERATED
→ BACKTEST
→ REVIEW
Current Development Status

当前仓库已经包含一个可安装、可测试的 MVP 开发骨架：

- Pydantic 数据契约：MarketSignal、StrategyManifest、RiskAuditResult、BacktestReport、ReviewCase、WorkflowRun
- Market Scout mock：生成 volume_spike / funding_oi_extreme 信号，并按 rank_score 过滤
- mock Researcher：根据 MarketSignal 生成 Freqtrade strategy.py
- Researcher prompt / response 日志：保留结构化 prompt 与 response log
- static Risk Auditor：检查 stoploss、martingale、DCA、lookahead、动态执行和外部网络调用
- mock Backtester：生成结构化 BacktestReport
- Freqtrade CLI 边界：策略名解析、backtesting 命令构建、结果 JSON 解析
- Binance 真实数据边界：OHLCV、funding rate、open interest、orderbook snapshot
- 数据质量检查：缺失、异常价格/成交量、orderbook 异常
- 真实数据 MarketSignal builder：从 Binance 数据生成可追溯 signal
- Paper Trading：paper portfolio、paper order、paper fill、paper position、paper trading report
- Paper vs Backtest 对比：比较 total_return / profit_factor，并决定 LIVE_CANDIDATE 或 RETIRED
- Paper 状态机：HUMAN_REVIEW_REQUIRED → PAPER_TRADING → PAPER_EVALUATION → LIVE_CANDIDATE / RETIRED
- Strategy Registry：策略版本、生命周期、晋级/淘汰、衰减和重复检测
- Reviewer 强化：trades 解析、regime 复盘、signal rank 与收益对齐分析
- 数据资产化：trades、trade summaries、prompt logs、model responses、enhanced review metrics
- Researcher 质量提升：模板库、指标白名单、多候选生成、候选排名、重复候选惩罚
- Backtest 可信度：walk-forward、out-of-sample、参数敏感性、fee/slippage、overfitting 检测
- 动态组合风控：exposure、daily loss、drawdown、correlation、concentration、kill switch、cooldown、volatility sizing
- Reviewer：生成 ReviewCase，并写入内存 ReviewStore
- SQLAlchemy 存储层：signals、strategies、risk_audits、backtests、reviews、workflow_runs
- ReviewCase 查询：支持内存 mock store 和 SQL repository
- 分阶段 flows：scout、research、risk_audit、backtest、review
- main MVP flow：串联 Signal → Strategy → Risk Audit → Backtest → Review，并可选落库
- pytest 测试覆盖核心模型、风控审查、存储层、Scout、分阶段 flows、Backtester CLI 和端到端 mock flow

Local Development

```bash
python3 -m venv .venv
./.venv/bin/pip install '.[dev]'
./.venv/bin/python -m pytest
```

当前预期测试结果：

```text
58 passed
```

尝试使用 Binance 真实公开数据生成 MarketSignal：

```bash
./.venv/bin/python scripts/run_real_data_scout.py --symbol BTC/USDT --interval 5m
```

该命令会把原始数据和质量报告写入本地 `market_data.sqlite3`，并在终端输出 quality report 与生成的 signal。
如果当前行情未达到默认 `--min-rank 70`，`signal` 会是 `null`，这是正常的过滤行为。可用低阈值做 smoke test：

```bash
./.venv/bin/python scripts/run_real_data_scout.py --symbol BTC/USDT --interval 5m --min-rank 1
```

MVP 阶段已完成到 mock 可运行闭环。继续接入真实环境前需要准备：

- 可用的 Postgres / Qdrant 连接地址
- Freqtrade 与历史行情数据
- LLM API key 与模型选择
- n8n / Prefect 运行环境
- 稳定可访问 Binance public API 的网络环境
- Dashboard 阶段需要确认 UI 技术栈并安装对应运行依赖

导出 Pydantic JSON Schema：

```bash
./.venv/bin/python scripts/export_json_schemas.py
```

注意：当前实现为了适配本机默认 Python 3.9，代码兼容 `>=3.9`。生产环境仍建议使用 Python 3.11+。

Installation
1. Clone Repository
git clone https://github.com/your-org/quant-agent-platform.git

cd quant-agent-platform
2. Install Dependencies

推荐：

Python 3.11+
Poetry
poetry install

或：

pip install -r requirements.txt
3. Configure Environment

复制：

cp .env.example .env

填写：

OPENAI_API_KEY=
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4

POSTGRES_URL=
QDRANT_URL=

BINANCE_API_KEY=
BINANCE_API_SECRET=
Running The MVP
Start PostgreSQL
docker compose up postgres -d
Start Qdrant
docker compose up qdrant -d
Start Prefect
prefect server start
Run Scout
python app/services/scout/run.py
Run Research Flow
python app/flows/research_flow.py
Run Backtest
python app/flows/backtest_flow.py
Example Workflow
1. Scout Detects Signal
{
  "symbol": "ETH/USDT",
  "signal_type": "funding_oi_extreme",
  "rank_score": 89
}
2. Researcher Generates Strategy

输出：

freqtrade_user_data/strategies/
    FundingExtremeV1.py
3. Risk Auditor Reviews
{
  "approved": true
}
4. Backtester Executes
freqtrade backtesting \
  --strategy FundingExtremeV1
5. Reviewer Writes Lessons
{
  "pattern": "Funding extreme works poorly during strong trend continuation"
}
Risk Philosophy

系统设计原则：

宁可错过机会，也不要允许危险策略进入执行层。

任何策略都必须：

有 stoploss
有 position limit
有 drawdown limit
可解释
可复盘
可审计
Why Human-in-the-Loop

我们不相信：

LLM 可以稳定地产生真实 alpha。

因此：

Agent 负责提出假设
回测负责验证
Reviewer 负责积累经验
人类负责最终审批
Future Roadmap
Phase 1 (Current MVP)
Scout
Researcher
Risk Auditor
Backtester
Reviewer
RAG Learning Loop
Phase 2
Paper Trading
Live Signal Dashboard
Multi-exchange Support
Portfolio Management
Advanced Risk Engine
Phase 3
Temporal Durable Workflows
Distributed Workers
GPU Research Cluster
Multi-strategy Portfolio Optimization
Event-driven Alpha Engine
Long-Term Vision

最终目标：

建立一个持续进化的量化研究操作系统。

不是：

一个自动下单机器人。
Development Principles
1. Everything Is Structured

所有 Agent 必须：

输入结构化 JSON
输出结构化 JSON
使用 Pydantic Model
2. Every Decision Must Be Auditable

必须保留：

Prompt
Response
Strategy Version
Backtest Result
Risk Audit Result
3. Failures Are Assets

失败案例不是垃圾数据。

失败案例是：

下一次策略生成的重要上下文。

Testing
pytest
Contributing

欢迎：

Alpha Research
Market Structure Analysis
Risk Engine
LLM Workflow
RAG Improvement
Backtest Optimization
Disclaimer

本项目仅用于研究与教育目的。

不构成投资建议。

自动交易存在高风险。

请勿直接用于实盘资金。

License

MIT License
