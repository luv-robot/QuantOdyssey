# Quant Agent Platform

Multi-Agent Quantitative Research & Strategy Discovery Platform

一个用于自动发现量化交易机会、生成策略、回测验证、风险审查与持续复盘学习的多 Agent 平台。

---

# Vision

本项目目标不是“自动生成交易代码”，而是建立一个：

> 可持续发现 alpha、自动淘汰劣质策略、积累失败经验、持续迭代进化的量化研究系统。

平台采用：

- Multi-Agent 协作架构
- LLM + RAG 策略研究
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
自动生成候选策略
自动进行静态风险审查
自动执行回测
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

2. Strategy Researcher

负责：

检索历史成功案例
调用 LLM 生成策略
输出 Freqtrade Strategy

输出：

strategy.py
strategy_manifest.json
assumptions.md
failure_modes.md
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
