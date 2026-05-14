# Research OS

QuantOdyssey 的长期定位是研究员系统，不是交易员系统。

系统的核心价值不是让 LLM 自动发明 alpha，而是把人类可理解、可反驳的市场 thesis 转化为可执行实验、可复盘证据和可积累研究资产。LLM/agent 负责结构化、实现、测试、总结和提出下一步研究问题；人类负责提出初始方向、判断市场逻辑是否可信，以及决定是否继续投入理解。

长期产品目标见 [Product Vision](product_vision.md)。QuantOdyssey 应逐步发展为业余量化研究者、小型研究小组和独立开发者可使用的平台，提供 AI 主导的策略分析评价，而不是简单的数据反馈。

## Research Philosophy

策略研究优先寻找市场参与者的结构性脆弱点：

```text
谁拥挤？
谁迟到？
谁被迫交易？
谁持仓成本不可持续？
谁的止损、清算或流动性需求集中？
谁在错误位置承担了过多风险？
```

平台不把策略研究简化为预测下一根 K 线。更重要的问题是：

```text
在某个市场结构下，哪一类参与者可能犯错或被迫交易？
这个错误是否可观察？
这个错误是否能被系统化定义为事件？
这个事件之后的收益、回撤、失败模式是否可验证？
```

## Human Thesis, Agent Implementation

ResearchThesis 仍保持开放格式，避免把平台过度收窄为单一策略范式。平台需要兼容常见趋势、反转、事件、套利、风控和过滤类策略。

但是系统在内部应尽量补全这些研究元数据：

```text
strategy_family
evaluation_type
event_definition
data_sufficiency_level
expected_regime
failure_modes
invalidation_condition
baseline_set
```

这些字段可以由系统从 thesis、MarketSignal 和历史案例中推断，也可以在后续 UI 中允许人工覆盖。

## Strategy Families

第一阶段不提前押注单一策略族。平台应同时测试多个策略族，统计机会频率、样本质量、初步 edge、失败原因，然后深入探索相对高频且证据更好的方向。

优先策略族：

| ID | Family | Core idea | First data level |
| --- | --- | --- | --- |
| S1 | Liquidity Sweep Reversal | 扫过关键位后，止损/清算/追单释放，价格 reclaim | L0 weak version, L2 preferred |
| S2 | Liquidation Cascade Reversal | 杠杆集中导致连锁清算，极端偏离后均值回归 | L0 proxy, L2 preferred |
| S3 | Funding Crowding Fade | 极端 funding + 拥挤 OI + 价格无法延续后反向惩罚 | L1 minimum |
| S4 | Failed Breakout Punishment | 明显突破未被接受，追单者被惩罚 | L0 usable |
| S5 | Event Overreaction Fade | 事件冲击后反应过度，价格回归 | L0/L3 depending on event source |
| S6 | Unlock/Airdrop Expectation Trap | 解锁、空投、预期兑现导致拥挤交易失效 | L3 preferred |
| S7 | Market Maker Inventory Reversal | 做市库存压力释放后的短期回归 | L2/L3 preferred |
| S8 | Basis/Funding Dislocation Reversion | 基差或 funding 脱离可持续范围后回归 | L1 minimum |
| S9 | Low Liquidity Impact Reversion | 低流动性导致价格冲击后回撤 | L0 proxy, L2 preferred |
| S10 | Narrative Crowding Fade | 叙事过度拥挤后的反向回撤 | L3 preferred |
| S11 | Trend Trap Continuation | 看似反转实为趋势陷阱，趋势继续惩罚逆势者 | L0 usable |
| S12 | VWAP Exhaustion Reversion | 偏离 VWAP 后动能衰竭回归 | L0 usable |

## Data Sufficiency Levels

OHLCV 可以满足最低限度的初筛和证伪，但不能支持完整结论。每个研究结果必须标记数据充分性，避免把弱代理变量误认为真实机制。

| Level | Data | Meaning |
| --- | --- | --- |
| L0 | OHLCV only | 只能做价格行为和形态代理验证。适合初筛、证伪、发现事件频率，不适合宣称 crowding/forced flow 已被证明。 |
| L1 | OHLCV + funding + open interest | 可以开始验证 crowding、持仓成本和杠杆脆弱性。 |
| L2 | L1 + liquidation + orderbook/trades | 可以验证 sweep、cascade、absorption、forced flow。 |
| L3 | L2 + on-chain / wallet / narrative / event data | 可以研究中慢周期结构性脆弱、资金流和叙事拥挤。 |

第三方数据源按证据需求逐步引入。Nansen、Glassnode 等数据源只有在系统证明“没有它就无法回答关键研究问题”之后再接入。

Funding Crowding Fade 的第一版事件生成应优先使用免费 L1 数据：

```text
Freqtrade futures OHLCV
Freqtrade futures funding_rate
Binance public open interest when available
```

如果历史 open interest 尚未进入回测 dataframe，系统可以使用 volume percentile 作为临时参与度代理，
但必须把 `historical_open_interest` 标入 `missing_evidence`，不能把代理变量叙述成真实 OI 证据。

## Market Context Engine

Market Context Engine 是共享研究上下文，不是独立 alpha。

第一版只使用四类 regime：

```text
NORMAL
STRONG_TREND
CRASH
CHAOS
```

推荐输出：

```json
{
  "context_id": "ctx_001",
  "regime": "STRONG_TREND",
  "regime_confidence": 0.72,
  "trend_score": 81,
  "fragility_long_score": 44,
  "fragility_short_score": 67,
  "volatility_score": 63,
  "liquidity_score": 58,
  "crash_risk_score": 21,
  "data_sufficiency_level": "L0"
}
```

## Trend Score

Trend Score 判断趋势是否存在、是否健康、是否接近衰竭。第一版可以使用 OHLCV 代理变量：

```text
price velocity
path efficiency
pullback depth
breakout acceptance
new high / new low frequency
ATR-normalized movement
volume-adjusted price impact proxy
```

成交量不应直接等同于趋势方向。成交量更适合作为趋势质量、参与度、衰竭风险和拥挤风险的辅助证据。

## Fragility Score

Fragility Score 不回答“谁更强”，而回答“谁更脆弱、谁更可能被迫交易”。

第一版应区分：

```text
long_fragility_score
short_fragility_score
punishment_bias = long_fragility_score - short_fragility_score
```

在 L0 数据下，Fragility 只能是价格脆弱性代理。例如突破失败、长影线、极端偏离、回撤效率恶化。真实 crowding、funding pressure、OI fuel 和 liquidation pressure 至少需要 L1/L2 数据。

## Permission Layer

现阶段 QuantOdyssey 是策略研究平台，不是投资计划生成器。因此 Permission Layer 暂时只做风险和上下文评分，不自动禁用策略、不调整仓位、不生成交易权限。

第一版输出建议：

```json
{
  "strategy_family": "failed_breakout_punishment",
  "context_id": "ctx_001",
  "context_risk_score": 73,
  "permission_note": "Research-only score. No automatic trading action.",
  "risk_reasons": [
    "strong trend regime may reduce reversal strategy reliability",
    "volatility is elevated"
  ]
}
```

未来如果进入 paper/live 研究阶段，可以再把 Permission Layer 扩展为 disable、reduce、watch_only、enabled 等动作。但当前阶段只保存评分与解释。

## Watchlist Principle

低频策略样本不足时，不应直接判定失败。系统应进入 Watchlist，继续收集事件、记录错过机会和失败案例。

```text
insufficient sample != failed thesis
```

进入 Watchlist 的常见原因：

```text
event_count too low
trade_count too low
data_sufficiency_level too weak
key external data unavailable
regime coverage insufficient
symbol coverage insufficient
```

## Third-Party Data Policy

外部数据源按以下顺序考虑：

1. Funding、open interest、basis
2. Liquidation、orderbook、trades
3. On-chain、wallet、smart money、exchange flows
4. Narrative、news、social、event calendar

引入原则：

```text
先用现有数据定义问题。
如果问题无法被现有数据回答，再引入新数据。
引入新数据前，必须说明它验证哪个假设、替代哪个代理变量、改善哪个失败模式。
```

Nansen 和 Glassnode 接口应预留，但不应在没有明确证据需求前成为平台复杂度来源。

## Connection to Execution

QuantOdyssey 当前阶段仍然是研究平台，但研究资产必须能在未来连接到独立下单系统。

边界原则：

```text
QuantOdyssey outputs DeploymentCandidate.
Execution system outputs orders.
```

研究平台可以输出：

```text
strategy code hash
research evidence
approved symbols and timeframes
expected and blocked regimes
risk constraints
audit trail
human approval status
```

研究平台不输出：

```text
final position size
account-level exposure
live order instruction
exchange API call
capital allocation decision
```

详细接口见 [Execution Integration](execution_integration.md)。
