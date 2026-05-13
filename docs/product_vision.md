# Product Vision

QuantOdyssey 的长期目标不是个人脚本集合，也不是自动交易机器人，而是一个多人可应用的量化研究平台。

目标用户包括：

```text
业余量化研究者
小型研究小组
独立交易者
希望验证市场想法的开发者
希望把策略研究流程规范化的团队
```

Early users are expected to be AI-era independent quant researchers:

```text
有编程能力
有投资常识
能使用 AI / vibe coding 快速实现策略
缺少系统化验证流程
缺少高质量同行反馈
需要一个温和但严苛的 AI 研究伙伴
```

These users may be able to write strategy code, but they need help avoiding unreviewed ideas,
overfit indicator stacking, weak baselines, sample bias, and premature confidence.

平台的核心价值是帮助用户把市场想法变成可验证、可复盘、可比较、可积累的研究资产。

## Product Positioning

QuantOdyssey should help users answer:

```text
我的策略想法是否有可验证的统计证据？
它在哪些市场环境中有效或失效？
它是否只是过拟合？
它和简单 baseline 相比是否真的更好？
它失败时通常失败在哪里？
我下一步应该如何改进这个研究方向？
```

The product should not stop at:

```text
here is a backtest number
here is a chart
here is profit factor
here is a generated strategy file
```

Instead, it should provide AI-led analysis and evaluation:

```text
strategy assumption analysis
failure mode diagnosis
baseline comparison interpretation
regime-specific explanation
data sufficiency review
overfitting and robustness critique
next experiment suggestions
watchlist and retirement reasoning
```

## AI Role

AI is not positioned as an autonomous alpha oracle.

AI should behave like a research analyst:

```text
understand the thesis
translate it into testable structure
generate implementation variants
evaluate evidence quality
explain why a strategy passed or failed
identify missing data
compare against baselines
suggest next experiments
summarize reusable lessons
```

The user should feel that the platform is helping them think better, not merely returning data.

## User Journey

The initial user journey should start from natural-language thesis submission.

```text
Submit natural-language thesis
-> AI-generated research design draft
-> user confirms or edits the design
-> system infers strategy family and evaluation type
-> candidate strategy generation
-> risk audit
-> backtest / validation / Monte Carlo where appropriate
-> ReviewSession
-> user answers AI questions or challenges the interpretation
-> next experiments or saved finding
```

Future users may also enter through public content:

```text
view public strategy arena result
-> inspect objective score breakdown
-> read public self-description and system-inferred profile
-> fork the research direction privately
-> submit their own thesis or variant
```

V1 input scope:

```text
Natural-language ResearchThesis only.
```

V2 input scope:

```text
Freqtrade-compatible Python strategy file upload.
```

Out of scope for the near term:

```text
multi-language strategy import
TradingView Pine conversion
notebook-to-strategy automation
generic SDK support
```

## ReviewSession

The core product output is not a static report. It is an evidence-first research dialogue.

The report and scorecard are the entry point. The valuable product experience is the interactive
review that helps the user understand support, opposition, blind spots, and next experiments.

ReviewSession should include:

```text
reproducible scorecard
Research Maturity Score
evidence for the thesis
evidence against the thesis
blind spots and likely overlooked risks
hypothesis drift check
AI questions
next experiments
user responses or objections
final research notes
```

AI may actively ask questions. It may suggest clarifying the thesis before running experiments, but
should not block the user from running them. If the user disagrees, the AI should acknowledge the
objection, record it, and move toward the next useful question or experiment.

Formal AI criticism must cite evidence, such as:

```text
backtest metrics
baseline comparison
regime breakdown
parameter sensitivity
trade concentration
data sufficiency limits
historical review cases
strategy code structure
```

The tone should be:

```text
warm but strict
evidence-first
non-flattering
non-authoritarian
no unsupported criticism
no investment advice
```

Private ReviewSession commentary should remain private to the user or team. Strategy Arena should
show objective metrics and classifications, not private AI subjective critique.

## Thesis Pre-Review

The minimum viable experience should begin before backtesting.

After a user submits a natural-language thesis, AI should first ask whether the research structure
is complete, whether conditions are clearly defined, and whether the idea is too close to common
public strategies.

V1 Pre-Review checks:

```text
structure completeness
condition clarity
commonness / indicator-stacking risk
key missing questions
assumptions if the user proceeds anyway
hypothesis drift risk
```

Pre-Review is not a gatekeeper. It should create healthy research friction without blocking the
user. The user may answer questions or proceed with assumptions.

Rules:

```text
prioritize the most important questions
the UI may highlight the top 3 questions, but the system should not hard-limit itself when more questions are needed
do not say the strategy is good or bad
record unresolved questions
record AI assumptions if the user proceeds
carry unresolved assumptions into the later ReviewSession
```

The V1 loop is:

```text
Submit Thesis
-> Thesis Pre-Review
-> Research Design Draft
-> Candidate Strategy Generation
-> Backtest / Validation
-> ReviewSession
```

## Research Maturity Score

QuantOdyssey should use `Research Maturity Score`, not a strategy credit score.

The score does not mean:

```text
this strategy is trustworthy
this strategy should receive capital
this strategy will make money
```

It means:

```text
this research idea has advanced to a certain evidence stage
```

Recommended dimensions:

```text
thesis_clarity
data_sufficiency
sample_maturity
baseline_advantage
robustness
regime_stability
failure_understanding
implementation_safety
overfit_risk
```

Research Maturity should explain blockers instead of issuing a hard viability verdict. Example:

```text
Research Maturity: 62 / 100
Stage: promising but immature
Main blockers:
- sample count is still low
- baseline advantage is weak
- performance depends on a narrow parameter range
- stated crowding thesis lacks funding/OI evidence
```

## Multi-User Direction

Future versions should support multiple researchers and teams.

Important concepts:

```text
workspace
project
research thesis
strategy family
experiment run
review case
watchlist
arena submission
shared knowledge base
permissions and audit trail
```

Multi-user design requirements:

```text
research artifacts must be attributable
strategy versions must be immutable after evaluation
comments and human decisions should be preserved
AI analysis should be reproducible from stored inputs
private research should remain private by default
shared arenas require explicit submission
```

## Strategy Arena

Strategy Arena is a possible commercialization path.

The idea:

```text
Users submit strategies or theses.
The platform evaluates them under standardized protocols.
Results are compared in a fair, type-aware arena.
AI produces analysis, critique, and improvement suggestions.
Users can learn from rankings, failure cases, and anonymized patterns.
```

Arena should not be a naive leaderboard based only on total return.

Arena scoring is intentionally not finalized yet. The near-term requirement is to preserve enough
objective evaluation data to support future scoring research.

It should compare strategies by:

```text
evaluation_type
market regime
symbol universe
timeframe
data sufficiency level
baseline advantage
robustness
drawdown
fee and slippage sensitivity
sample maturity
failure pattern
explainability
```

Possible arena tracks:

```text
continuous alpha
event-driven alpha
tail / crisis alpha
permission or filter strategies
low-frequency thesis watchlist
student / hobbyist research track
small-team private arena
public benchmark arena
```

Privacy and publication rules:

```text
strategy details are private by default
public submissions may expose strategy type, user self-description, system-inferred profile, and result metrics
private AI review commentary is not publicly shown in Arena
public scoring should rely on objective metrics and clearly labeled classifications
```

## Commercialization Principles

The commercial version should sell better research process, not magical alpha.

Potential paid value:

```text
standardized strategy validation
AI-generated research critique
multi-strategy comparison
team workspace and audit trail
private strategy arena
advanced robustness tests
external data connectors
scheduled research digests
collaborative review library
```

Boundaries:

```text
do not market as guaranteed profit
do not imply AI can reliably discover alpha alone
do not blur research platform with investment advice
do not expose private strategies without explicit submission
```

## Product North Star

QuantOdyssey should become:

```text
An AI-assisted research operating system for validating, comparing, and improving quantitative strategy ideas.
```

The platform succeeds when users can move from intuition to evidence faster, understand failures more clearly, and avoid repeatedly testing the same weak assumptions.
