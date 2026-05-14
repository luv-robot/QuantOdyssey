# Evaluation Profiles

QuantOdyssey 不能用同一套指标评价所有策略。连续 alpha、事件驱动策略、尾部风险策略和风控过滤器的目标不同，样本结构不同，失败成本也不同。

本文件定义策略评价的基础规范。

## Research Maturity Score

策略研究输出应包含 `Research Maturity Score`。它不是信用评分，也不是投资建议。

Research Maturity Score 评价的是研究成熟度：

```text
这个 thesis 是否被清楚定义？
数据是否足够支持它声称的机制？
样本是否成熟？
是否真的优于合适 baseline？
是否经过基本鲁棒性验证？
是否知道主要失败模式？
```

推荐维度：

| Dimension | Meaning |
| --- | --- |
| `thesis_clarity` | 研究假设是否清楚、可反驳、可测试 |
| `data_sufficiency` | 当前数据等级是否足以验证该 thesis |
| `sample_maturity` | 事件数、交易数、市场覆盖是否足够 |
| `baseline_advantage` | 是否优于类型匹配的 baseline |
| `robustness` | walk-forward、OOS、Monte Carlo、参数扰动是否稳定 |
| `regime_stability` | 不同市场状态下是否有可解释表现 |
| `failure_understanding` | 是否已经识别主要失败模式 |
| `implementation_safety` | 代码和策略规则是否安全、可审计 |
| `overfit_risk` | 指标堆叠、参数窄区间、样本选择等过拟合风险 |

输出应避免武断结论。推荐表达：

```text
Research Maturity: 62 / 100
Stage: promising but immature
Main blockers: weak baseline advantage, insufficient samples, narrow parameter stability.
```

## Strategy Evaluation Types

每个策略或 thesis 都应尽量分配一个 `evaluation_type`。该字段可以由系统根据策略族自动推断，也可以由人工覆盖。

| Type | Purpose | Typical examples | Primary question |
| --- | --- | --- | --- |
| `continuous_alpha` | 持续产生交易信号 | 趋势跟随、均值回归、动量轮动 | 长期统计优势是否稳定？ |
| `event_driven_alpha` | 只在特定事件后交易 | sweep、failed breakout、funding crowding fade | 在合格事件内是否有 edge？ |
| `tail_or_crisis_alpha` | 在极端环境中保护或获利 | crash reversal、liquidation cascade | 极端行情下是否改善尾部结果？ |
| `permission_or_filter` | 过滤错误环境或降低风险 | regime filter、context risk score | 是否减少错误交易和尾部损失？ |

## Event Episode

事件驱动策略必须建立 `event_episode`，而不是只记录交易。

事件由系统根据 `strategy_family` 自动生成候选定义。人工可以后续覆盖。

推荐字段：

```json
{
  "event_id": "event_001",
  "strategy_family": "failed_breakout_punishment",
  "symbol": "BTC/USDT",
  "timeframe": "5m",
  "event_start": "2026-05-10T10:00:00Z",
  "event_end": "2026-05-10T12:00:00Z",
  "direction": "short",
  "event_quality_score": 78,
  "trigger_features": {
    "breakout_level": 65000,
    "breakout_distance_atr": 0.8,
    "close_back_inside_range": true,
    "volume_zscore": 2.1
  },
  "data_sufficiency_level": "L0"
}
```

## Default Event Definitions

第一阶段事件定义使用可解释、低复杂度规则，优先统计机会频率和基础可行性。

### S1 Liquidity Sweep Reversal

L0 代理定义：

```text
price trades beyond recent swing high/low
wick returns back inside the prior range
close reclaims the level within N candles
range or volume is above recent baseline
```

局限：

```text
OHLCV cannot prove real stop loss, liquidation, or orderbook absorption.
```

### S3 Funding Crowding Fade

最低数据要求为 L1。

```text
funding percentile is extreme
open interest is elevated or rising
price fails to extend in crowded direction
price closes back below/above trigger level
```

如果只有 L0 数据，只能生成 price-stall proxy，不应标记为已验证 crowding。

### S4 Failed Breakout Punishment

L0 可用定义：

```text
price breaks visible N-bar high/low
breakout candle closes weak or next candles reject
close returns inside range
follow-through fails within M candles
```

### S11 Trend Trap Continuation

L0 可用定义：

```text
trend_score is high
countertrend pullback fails to gain path efficiency
price reclaims trend direction level
breakout acceptance resumes
```

### S2 Liquidation Cascade Reversal

L0 只能做 crash wick reversal proxy。

```text
large ATR-normalized move
long wick or extreme close location reversal
volume spike
rapid partial retrace
```

完整验证需要 liquidation 或 OI 数据。

## Metrics by Evaluation Type

### Continuous Alpha

主要指标：

```text
profit_factor
sharpe_ratio
sortino_ratio
max_drawdown
trade_count
fee_slippage_adjusted_return
walk_forward_score
out_of_sample_score
```

### Event-Driven Alpha

主要指标：

```text
event_count
qualified_event_count
trigger_count
trade_count
event_hit_rate
event_profit_factor
average_r_multiple
payoff_skew
MAE / MFE
opportunity_capture_rate
false_positive_cost
false_negative_cost
missed_opportunity_count
skip_quality_score
```

### Tail or Crisis Alpha

主要指标：

```text
tail_event_count
drawdown_reduction
crisis_period_return
time_to_recovery
worst_case_trade
left_tail_exposure
false_alarm_cost
```

### Permission or Filter

主要指标：

```text
bad_trade_reduction
drawdown_reduction
missed_good_trade_cost
net_filter_value
false_disable_rate
false_allow_rate
regime_bucket_impact
```

## Baselines

Baseline 必须匹配策略类型。

### Continuous Alpha Baselines

```text
no_trade
buy_and_hold
simple_momentum
simple_mean_reversion
random_entry_same_frequency
```

### Event-Driven Baselines

```text
no_trade
naive_event_entry
randomized_entry_within_event_window
opposite_direction
simple_rule_version
```

不要用 buy-and-hold 作为事件驱动策略的唯一 baseline。

For Funding Crowding Fade, QuantOdyssey now prefers event-level baselines when matching OHLCV and
funding files are available:

```text
funding_extreme_only_event
funding_plus_oi_event
simple_failed_breakout_event
opposite_direction_event
```

If historical open interest is unavailable, the event-level baseline may use volume as a temporary
participation proxy, but ReviewSession must mark `historical_open_interest` as missing evidence.

### Permission or Filter Baselines

```text
strategy_without_filter
strategy_with_random_filter
strategy_with_simple_volatility_filter
```

## Monte Carlo Policy

Monte Carlo 方法必须匹配样本结构。

| Evaluation type | Preferred method |
| --- | --- |
| `continuous_alpha` | trade resampling, block bootstrap |
| `event_driven_alpha` | event episode resampling |
| `tail_or_crisis_alpha` | stress period resampling, scenario replay |
| `permission_or_filter` | paired comparison of filtered vs unfiltered trades |

大规模 Monte Carlo、参数网格和跨品种批量验证必须进入人工确认门槛。

## Watchlist Rules

低频策略或证据不足策略进入 Watchlist，而不是立即淘汰。

Watchlist 状态应保留：

```text
reason
required_more_data
minimum_event_count
minimum_trade_count
missing_data_source
next_review_date
```

常见 Watchlist 原因：

```text
insufficient events
insufficient trades
missing funding/OI/liquidation data
insufficient regime coverage
unclear baseline advantage
promising but not statistically mature
```

## Promotion and Rejection

研究阶段的结论不应只有 pass/fail。

推荐状态：

```text
REJECTED
WATCHLIST
NEEDS_BETTER_DATA
NEEDS_REDEFINITION
ROBUST_ENOUGH_FOR_DEEPER_TEST
PAPER_RESEARCH_CANDIDATE
```

现阶段的晋级含义是“值得更深入研究”，不是“值得投入资金”。
