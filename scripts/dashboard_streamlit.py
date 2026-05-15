import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app.flows.human_research_pipeline import run_human_research_pipeline  # noqa: E402
from app.models import (  # noqa: E402
    MarketSignal,
    MonteCarloBacktestConfig,
    PreReviewStatus,
    ResearchThesis,
    ThesisStatus,
)
from app.services.operations import run_health_checks  # noqa: E402
from app.services.harness import build_baseline_implied_regime_report, build_strategy_family_baseline_board  # noqa: E402
from app.services.market_data import build_orderflow_health_report, load_freqtrade_ohlcv  # noqa: E402
from app.services.metrics import performance_metric_registry  # noqa: E402
from app.services.researcher import build_research_design_draft, build_thesis_pre_review  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


DEFAULT_DB_URL = "sqlite+pysqlite:///market_data.sqlite3"
DASHBOARD_ICON_PATH = ROOT / "public" / "assets" / "quantodyssey-mark.svg"
KEY_TABLES = [
    "research_theses",
    "thesis_pre_reviews",
    "research_design_drafts",
    "event_episodes",
    "research_asset_index",
    "research_findings",
    "research_tasks",
    "research_harness_cycles",
    "event_definition_sensitivity_reports",
    "event_definition_universe_reports",
    "failed_breakout_sensitivity_reports",
    "failed_breakout_universe_reports",
    "strategy_family_walk_forward_reports",
    "strategy_family_monte_carlo_reports",
    "strategy_family_orderflow_acceptance_reports",
    "orderflow_bars",
    "signals",
    "market_regime_snapshots",
    "data_quality_reports",
    "strategy_registry",
    "experiment_manifests",
    "experiment_queue",
    "baseline_comparisons",
    "review_sessions",
    "robustness_reports",
    "cross_symbol_validations",
    "real_backtest_validation_suites",
    "backtests",
    "monte_carlo_backtests",
    "paper_trading_reports",
    "paper_trading_plans",
    "reviews",
    "negative_result_cases",
    "portfolio_risk_reports",
    "resource_budget_reports",
    "enhanced_review_metrics",
]


def connect_database():
    database_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    return create_engine(database_url), database_url


def table_count(engine, table_name: str) -> Optional[int]:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return None
    with engine.connect() as connection:
        return int(connection.execute(text(f"select count(*) from {table_name}")).scalar() or 0)


def recent_payloads(engine, table_name: str, limit: int = 20) -> list[str]:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return []
    with engine.connect() as connection:
        rows = connection.execute(
            text(f"select payload from {table_name} order by created_at desc limit :limit"),
            {"limit": limit},
        ).fetchall()
    return [row[0] for row in rows]


def recent_records(engine, table_name: str, limit: int = 20) -> list[dict]:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return []
    with engine.connect() as connection:
        rows = connection.execute(
            text(f"select payload from {table_name} order by created_at desc limit :limit"),
            {"limit": limit},
        ).fetchall()
    return [_json_load(row[0]) for row in rows]


def _json_load(payload: str) -> dict:
    import json

    try:
        return json.loads(payload)
    except Exception:
        return {"raw": payload}


def _lines(value: str, fallback: list[str]) -> list[str]:
    items = [line.strip() for line in value.splitlines() if line.strip()]
    return items or fallback


def render_research_pipeline(engine, database_url: str) -> None:
    st.subheader("Human-Led Research Pipeline")
    signals = recent_records(engine, "signals", limit=25)
    if not signals:
        st.info("No MarketSignal records found yet. Run the market data flow first.")
        return

    signal_options = {
        f"{item['signal_id']} | {item['symbol']} | rank {item['rank_score']} | {item['created_at']}": item
        for item in signals
    }
    with st.form("research_pipeline_form"):
        selected_label = st.selectbox("MarketSignal", list(signal_options))
        title = st.text_input("Thesis title", placeholder="Volume absorption continuation")
        market_observation = st.text_area(
            "Market observation",
            placeholder="What did you observe in price, volume, funding, liquidity, or regime?",
        )
        hypothesis = st.text_area(
            "Hypothesis",
            placeholder="Why should this observation create a repeatable edge?",
        )
        trade_logic = st.text_area(
            "Trade logic",
            placeholder="Entry, exit, filters, and risk idea in plain language.",
        )
        expected_regimes = st.text_area(
            "Expected regimes",
            value="trend continuation\nhigh relative volume",
        )
        invalidation_conditions = st.text_area(
            "Invalidation conditions",
            value="profit factor below threshold after fee/slippage\nMonte Carlo loss probability too high",
        )
        constraints = st.text_area(
            "Constraints",
            value="long-only\nno leverage increase\nmust define stoploss",
        )
        left, middle, right = st.columns(3)
        candidate_count = left.number_input("Candidates", min_value=1, max_value=5, value=3, step=1)
        mc_simulations = middle.number_input("MC simulations", min_value=10, max_value=100000, value=500)
        mc_horizon = right.number_input("MC horizon trades", min_value=1, max_value=10000, value=100)
        backtest_mode = st.selectbox("Backtest mode", ["real", "mock"], index=0)
        approve_expensive = st.checkbox("Approve expensive Monte Carlo if threshold is exceeded")
        pre_review_only = st.form_submit_button("Preview Research Design")
        submitted = st.form_submit_button("Run Research Pipeline")

    if not (pre_review_only or submitted):
        return
    if not all([title.strip(), market_observation.strip(), hypothesis.strip(), trade_logic.strip()]):
        st.error("Title, observation, hypothesis, and trade logic are required.")
        return

    signal = MarketSignal.model_validate(signal_options[selected_label])
    thesis = ResearchThesis(
        thesis_id=f"thesis_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}",
        title=title.strip(),
        status=ThesisStatus.READY_FOR_IMPLEMENTATION,
        market_observation=market_observation.strip(),
        hypothesis=hypothesis.strip(),
        trade_logic=trade_logic.strip(),
        expected_regimes=_lines(expected_regimes, ["unspecified"]),
        invalidation_conditions=_lines(invalidation_conditions, ["not specified"]),
        linked_signal_ids=[signal.signal_id],
        constraints=_lines(constraints, []),
    )
    repository = QuantRepository(database_url)
    pre_review = build_thesis_pre_review(thesis)
    research_design = build_research_design_draft(thesis, pre_review)
    repository.save_research_thesis(thesis)
    repository.save_thesis_pre_review(pre_review)
    repository.save_research_design_draft(research_design)

    st.write("### Thesis Pre-Review")
    status_method = {
        PreReviewStatus.READY_FOR_DESIGN: st.success,
        PreReviewStatus.CAN_PROCEED_WITH_ASSUMPTIONS: st.warning,
        PreReviewStatus.NEEDS_CLARIFICATION: st.error,
    }[pre_review.status]
    status_method(f"Pre-review status: `{pre_review.status.value}`")
    metric_cols = st.columns(3)
    metric_cols[0].metric("Completeness", f"{pre_review.completeness_score:.0f}")
    metric_cols[1].metric("Condition Clarity", f"{pre_review.condition_clarity_score:.0f}")
    metric_cols[2].metric("Commonness Risk", f"{pre_review.commonness_risk_score:.0f}")
    with st.expander("Pre-review details", expanded=True):
        st.json(pre_review.model_dump(mode="json"))
    st.write("### Research Design Draft")
    st.json(research_design.model_dump(mode="json"))

    if pre_review_only:
        st.info("Pre-review saved. Answer the questions or run the pipeline with these assumptions.")
        return

    with st.spinner("Running candidate generation, risk audit, backtest, Monte Carlo, and review..."):
        result = run_human_research_pipeline(
            thesis,
            signal,
            repository,
            candidate_count=int(candidate_count),
            monte_carlo_config=MonteCarloBacktestConfig(
                simulations=int(mc_simulations),
                horizon_trades=int(mc_horizon),
            ),
            approve_expensive_monte_carlo=approve_expensive,
            backtest_mode=backtest_mode,
        )

    if result.selected_candidate_id:
        st.success(f"Pipeline completed. Selected: `{result.selected_candidate_id}`")
    else:
        st.warning("Pipeline completed, but no candidate met the full criteria.")
    st.json(result.model_dump(mode="json"))


def render_research_workbench(engine, database_url: str) -> None:
    st.subheader("Personal Research Dashboard")
    recent_theses = recent_records(engine, "research_theses", limit=30)
    strategies = recent_records(engine, "strategies", limit=300)
    backtests = recent_records(engine, "backtests", limit=300)
    baselines = recent_records(engine, "baseline_comparisons", limit=300)
    robustness_reports = recent_records(engine, "robustness_reports", limit=300)
    review_sessions = recent_records(engine, "review_sessions", limit=300)
    latest_tasks = recent_records(engine, "research_tasks", limit=40)
    board, regime, error = _build_dashboard_baseline_regime()

    left_col, center_col, right_col = st.columns([0.82, 1.55, 0.86], gap="large")
    selected_thesis = recent_theses[0] if recent_theses else None
    selected_strategy = None

    with left_col:
        st.write("### 导航")
        if not recent_theses:
            st.info("还没有 thesis。请到 `Run Pipeline` 提交第一个假设。")
        else:
            thesis_options = {
                f"{item.get('title', item.get('thesis_id'))} · {item.get('status', 'unknown')}": item
                for item in recent_theses
            }
            selected_label = st.selectbox("我的 Thesis", list(thesis_options), label_visibility="collapsed")
            selected_thesis = thesis_options[selected_label]
            st.caption(f"`{selected_thesis.get('thesis_id')}`")
            linked = _strategies_for_thesis(strategies, selected_thesis.get("thesis_id"))
            st.write("**衍生可测试策略**")
            if linked:
                strategy_options = {
                    f"{item.get('name', item.get('strategy_id'))} · {item.get('status', 'generated')}": item
                    for item in linked
                }
                selected_strategy_label = st.radio(
                    "策略",
                    list(strategy_options),
                    label_visibility="collapsed",
                )
                selected_strategy = strategy_options[selected_strategy_label]
            else:
                st.info("这个 thesis 还没有生成策略。")
            with st.expander("Thesis → Strategy Tree", expanded=True):
                for thesis in recent_theses[:8]:
                    st.markdown(f"**{thesis.get('title', thesis.get('thesis_id'))}**")
                    children = _strategies_for_thesis(strategies, thesis.get("thesis_id"))
                    if not children:
                        st.caption("└─ no strategy yet")
                    for strategy in children[:5]:
                        st.caption(f"└─ {strategy.get('name', strategy.get('strategy_id'))}")

    with center_col:
        st.write("### 市场 Regime 要素评分")
        if error:
            st.warning(error)
        elif regime:
            _render_regime_score_bars(regime)
        else:
            st.info("暂无 regime 要素评分。")

        st.write("### 核心策略信息")
        visible_strategies = (
            _strategies_for_thesis(strategies, selected_thesis.get("thesis_id"))
            if selected_thesis
            else strategies[:10]
        )
        if visible_strategies:
            rows = _strategy_summary_rows(
                visible_strategies,
                backtests=backtests,
                baselines=baselines,
                robustness_reports=robustness_reports,
                review_sessions=review_sessions,
            )
            _render_strategy_summary_table(rows)
        else:
            st.info("暂无可汇总的策略。先运行 pipeline 生成候选策略。")

        if selected_strategy:
            st.write("### 选中策略摘要")
            strategy_id = selected_strategy.get("strategy_id")
            latest_backtest = _latest_by_field(backtests, "strategy_id", strategy_id)
            latest_review = _latest_by_field(review_sessions, "strategy_id", strategy_id)
            metrics = st.columns(5)
            metrics[0].metric("测试期", "-" if not latest_backtest else latest_backtest.get("timerange", "-"))
            metrics[1].metric("Return", _fmt_pct(None if not latest_backtest else latest_backtest.get("total_return")))
            metrics[2].metric("PF", _fmt_num(None if not latest_backtest else latest_backtest.get("profit_factor")))
            metrics[3].metric("MDD", _fmt_pct(None if not latest_backtest else latest_backtest.get("max_drawdown")))
            metrics[4].metric("AI Review", _short_review(latest_review))
            st.caption("详细 evidence、validation、AI Review 请进入 `Run Detail` 查看。")

    with right_col:
        st.write("### 系统行为")
        scoped_tasks = _tasks_for_scope(
            latest_tasks,
            thesis_id=None if not selected_thesis else selected_thesis.get("thesis_id"),
            strategy_id=None if not selected_strategy else selected_strategy.get("strategy_id"),
        )
        _render_harness_progress(scoped_tasks or latest_tasks[:8])

        st.write("### 快速入口")
        st.info("Run Detail：查看策略证据链")
        st.info("Metric Audit：查看指标公式")
        st.info("System Status：检查数据服务")


def render_metric_audit_registry() -> None:
    st.subheader("Metric Audit Registry")
    st.caption("Calculation principles and external calibration references for supervisor spot checks.")
    definitions = performance_metric_registry()
    rows = [
        {
            "metric": item.metric_id,
            "name": item.display_name,
            "category": item.category,
            "formula": item.formula,
            "unit": item.unit,
            "description": item.description,
        }
        for item in definitions
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.write("**Principle Self-Check**")
    for check in [
        "Sequential strategy returns must be compounded, not summed.",
        "Profit factor must use completed trade-level winners and losers, not symbol/timeframe cell returns.",
        "Maximum drawdown must come from an equity curve peak-to-trough path, not final return or worst single trade.",
        "Sharpe values must state whether they are annualized time-series Sharpe or per-trade proxy Sharpe.",
        "Any high metric with tiny sample count is weak evidence until sample sufficiency checks pass.",
    ]:
        st.write(f"- {check}")

    for item in definitions:
        with st.expander(f"{item.display_name} | {item.metric_id}", expanded=False):
            st.write(item.description)
            st.code(item.formula)
            st.write("**Implementation Notes**")
            for note in item.implementation_notes:
                st.write(f"- {note}")
            st.write("**Audit Checks**")
            for check in item.audit_checks:
                st.write(f"- {check}")
            st.write("**External References**")
            for reference in item.external_references:
                st.markdown(f"- [{reference['name']}]({reference['url']}): {reference['note']}")


def render_global_ai_assistant(engine) -> None:
    st.markdown("---")
    st.write("### 全能研究助手")
    st.caption("可以问当前页面、已有数据、指标公式、策略证据链或下一步任务。当前版本优先做站内路由和数据摘要。")
    with st.form("global_ai_assistant_form"):
        question = st.text_input(
            "Ask Quant Odyssey",
            placeholder="例如：这个策略为什么没通过？现在市场 regime 更偏什么？profit factor 怎么算？",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("提问")
    if not submitted or not question.strip():
        return
    st.info(_assistant_routing_answer(engine, question.strip()))


def _assistant_routing_answer(engine, question: str) -> str:
    lower = question.lower()
    theses = recent_records(engine, "research_theses", limit=3)
    tasks = recent_records(engine, "research_tasks", limit=5)
    board, regime, _ = _build_dashboard_baseline_regime()
    if any(key in lower for key in ["regime", "市场", "环境", "行情"]):
        if not regime:
            return "目前还没有可用的 regime 要素评分。请先检查 `Research Workbench` 中的 Market Regime 区域或运行 baseline-regime scan。"
        components = regime.get("component_scores", {})
        leader = max(components.items(), key=lambda item: item[1], default=("unknown", 0))
        return (
            f"当前应看作要素评分而非确定结论。领先因子是 `{leader[0]}`，分数 {leader[1]:.1f}。"
            "请看 `Research Workbench` 中间的 Regime 要素评分；需要公式口径时转到 `Metric Audit`。"
        )
    if any(key in lower for key in ["profit factor", "pf", "公式", "指标", "drawdown", "sharpe"]):
        return (
            "指标公式已集中到 `Metric Audit`。PF 使用 completed trade winners / completed trade losers；"
            "最大回撤来自 equity curve 峰谷，不再用最终收益或单个 cell 代替。"
        )
    if any(key in lower for key in ["策略", "strategy", "review", "为什么", "通过"]):
        latest = theses[0].get("title") if theses else "最新 thesis"
        return (
            f"请先在左侧 thesis→strategy 树选择策略；中间表只显示摘要。"
            f"要看 `{latest}` 的完整 evidence、validation summary、AI Review，请进入上方 `Run Detail` 标签。"
        )
    if any(key in lower for key in ["任务", "harness", "进度", "执行"]):
        if not tasks:
            return "Harness 暂无任务。提交 thesis 或运行 pipeline 后，右侧 `系统行为` 会显示任务进度。"
        return (
            f"当前最近有 {len(tasks)} 个 harness 任务。右侧 `系统行为` 显示执行进度；"
            "需要原始 payload 可以打开 `Human Approval` 或相关数据标签。"
        )
    if board and board.get("best_family"):
        return (
            f"我建议先看 `Research Workbench`：当前最佳通用 baseline 是 `{board['best_family']}`。"
            "若你的问题涉及策略细节，去 `Run Detail`；涉及计算口径，去 `Metric Audit`；涉及系统健康，去 `System Status`。"
        )
    return "我建议从 `Research Workbench` 开始；它会把导航、策略摘要、系统行为和可追问入口放在同一页。"


def render_research_run_detail(engine) -> None:
    st.subheader("Research Run Detail")
    theses = recent_records(engine, "research_theses", limit=50)
    if not theses:
        st.info("No research theses found yet.")
        return

    options = {
        f"{item['thesis_id']} | {item['status']} | {item['title']}": item
        for item in theses
    }
    selected = st.selectbox("Research thesis", list(options))
    thesis = options[selected]
    st.json(thesis)
    _render_related_payloads(engine, "thesis_pre_reviews", "thesis_id", thesis["thesis_id"], "Thesis Pre-Reviews")
    _render_related_payloads(engine, "research_design_drafts", "thesis_id", thesis["thesis_id"], "Research Design Drafts")
    _render_related_payloads(engine, "event_episodes", "thesis_id", thesis["thesis_id"], "Event Episodes")
    _render_related_payloads(
        engine,
        "event_definition_sensitivity_reports",
        "thesis_id",
        thesis["thesis_id"],
        "Event Definition Sensitivity Reports",
    )
    _render_related_payloads(
        engine,
        "event_definition_universe_reports",
        "thesis_id",
        thesis["thesis_id"],
        "Event Definition Universe Reports",
    )
    _render_related_payloads(
        engine,
        "failed_breakout_sensitivity_reports",
        "thesis_id",
        thesis["thesis_id"],
        "Failed Breakout Sensitivity Reports",
    )
    _render_related_payloads(
        engine,
        "failed_breakout_universe_reports",
        "thesis_id",
        thesis["thesis_id"],
        "Failed Breakout Universe Reports",
    )
    _render_strategy_family_validation_followups(engine, thesis["thesis_id"])

    strategies = _records_where_payload_field(
        engine,
        "strategies",
        "thesis_id",
        thesis["thesis_id"],
    )
    if not strategies:
        st.info("No strategies linked to this thesis yet.")
        return

    for strategy in strategies:
        strategy_id = strategy["strategy_id"]
        with st.expander(f"{strategy['name']} | {strategy_id}", expanded=True):
            st.write("**Strategy Manifest**")
            st.json(strategy)
            _render_single_payload(engine, "risk_audits", "strategy_id", strategy_id, "Risk Audit")
            _render_single_payload(
                engine,
                "experiment_manifests",
                "strategy_id",
                strategy_id,
                "Experiment Manifest",
            )
            _render_single_payload(
                engine,
                "baseline_comparisons",
                "strategy_id",
                strategy_id,
                "Baseline Comparison",
            )
            _render_single_payload(
                engine,
                "robustness_reports",
                "strategy_id",
                strategy_id,
                "Robustness Report",
            )
            _render_single_payload(engine, "backtests", "strategy_id", strategy_id, "Backtest")
            _render_single_payload(
                engine,
                "backtest_validations",
                "strategy_id",
                strategy_id,
                "Backtest Validation",
            )
            _render_single_payload(
                engine,
                "monte_carlo_backtests",
                "strategy_id",
                strategy_id,
                "Monte Carlo",
            )
            _render_single_payload(
                engine,
                "event_definition_sensitivity_reports",
                "strategy_id",
                strategy_id,
                "Event Definition Sensitivity",
            )
            _render_single_payload(
                engine,
                "failed_breakout_sensitivity_reports",
                "strategy_id",
                strategy_id,
                "Failed Breakout Sensitivity",
            )
            _render_single_payload(engine, "trade_summaries", "strategy_id", strategy_id, "Trade Summary")
            _render_single_payload(
                engine,
                "enhanced_review_metrics",
                "strategy_id",
                strategy_id,
                "Enhanced Review Metrics",
            )
            enhanced_metrics = _records_where_payload_field(
                engine,
                "enhanced_review_metrics",
                "strategy_id",
                strategy_id,
            )
            for metrics in enhanced_metrics:
                diagnoses = metrics.get("failure_diagnoses") or []
                if diagnoses:
                    st.write("**Failure Diagnosis**")
                    for diagnosis in diagnoses:
                        st.warning(f"{diagnosis['category']} | {diagnosis['severity']}")
                        for evidence in diagnosis.get("evidence", []):
                            st.caption(evidence)
                        st.info(diagnosis["recommendation"])
            reviews = _records_where_payload_field(engine, "reviews", "strategy_id", strategy_id)
            if reviews:
                st.write("**Review**")
                for review in reviews:
                    if review.get("failure_reason"):
                        st.error(review["failure_reason"])
                    st.json(review)
            review_sessions = _records_where_payload_field(
                engine,
                "review_sessions",
                "strategy_id",
                strategy_id,
            )
            if review_sessions:
                st.write("**Review Session**")
                for review_session in review_sessions:
                    maturity_score = review_session.get("maturity_score") or {}
                    if maturity_score:
                        st.metric("Maturity Score", f"{maturity_score.get('overall_score', 0):.2f}")
                    st.write("**Scorecard**")
                    st.json(review_session.get("scorecard") or {})
                    st.write("**Evidence For**")
                    st.json(review_session.get("evidence_for") or [])
                    st.write("**Evidence Against**")
                    st.json(review_session.get("evidence_against") or [])
                    st.write("**Blind Spots**")
                    st.json(review_session.get("blind_spots") or [])
                    st.write("**AI Questions**")
                    st.json(review_session.get("ai_questions") or [])
                    st.write("**Next Experiments**")
                    st.json(review_session.get("next_experiments") or [])
            findings = _records_where_payload_field(
                engine,
                "research_findings",
                "strategy_id",
                strategy_id,
            )
            if findings:
                st.write("**Harness Findings**")
                for finding in findings:
                    severity = finding.get("severity")
                    if severity == "high":
                        st.error(finding.get("summary"))
                    elif severity == "medium":
                        st.warning(finding.get("summary"))
                    else:
                        st.info(finding.get("summary"))
                    st.json(finding)
            tasks = _records_where_payload_field(
                engine,
                "research_tasks",
                "strategy_id",
                strategy_id,
            )
            if tasks:
                st.write("**Harness Next Tasks**")
                for task in tasks:
                    if task.get("approval_required"):
                        st.warning(f"{task.get('task_type')} requires approval")
                    else:
                        st.info(task.get("task_type"))
                    st.json(task)


def _records_where_payload_field(engine, table_name: str, field: str, value: str) -> list[dict]:
    records = recent_records(engine, table_name, limit=200)
    return [record for record in records if record.get(field) == value]


def _latest_record(engine, table_name: str) -> dict | None:
    records = recent_records(engine, table_name, limit=1)
    return records[0] if records else None


def _metric_count(engine, table_name: str) -> int | str:
    count = table_count(engine, table_name)
    return "n/a" if count is None else count


def _open_task_count(tasks: list[dict]) -> int:
    return sum(1 for task in tasks if task.get("status") not in {"completed", "cancelled"})


def _strategies_for_thesis(strategies: list[dict], thesis_id: str | None) -> list[dict]:
    if not thesis_id:
        return []
    return [item for item in strategies if item.get("thesis_id") == thesis_id]


def _latest_by_field(records: list[dict], field: str, value: str | None) -> dict | None:
    if not value:
        return None
    for record in records:
        if record.get(field) == value:
            return record
    return None


def _strategy_summary_rows(
    strategies: list[dict],
    *,
    backtests: list[dict],
    baselines: list[dict],
    robustness_reports: list[dict],
    review_sessions: list[dict],
) -> list[dict]:
    rows = []
    for strategy in strategies:
        strategy_id = strategy.get("strategy_id")
        backtest = _latest_by_field(backtests, "strategy_id", strategy_id)
        baseline = _latest_by_field(baselines, "strategy_id", strategy_id)
        robustness = _latest_by_field(robustness_reports, "strategy_id", strategy_id)
        review = _latest_by_field(review_sessions, "strategy_id", strategy_id)
        rows.append(
            {
                "strategy": strategy.get("name", strategy_id),
                "status": strategy.get("status", "-"),
                "timeframe": strategy.get("timeframe", "-"),
                "test_period": "-" if not backtest else backtest.get("timerange", "-"),
                "return": _fmt_pct(None if not backtest else backtest.get("total_return")),
                "pf": _fmt_num(None if not backtest else backtest.get("profit_factor")),
                "sharpe": _fmt_num(None if not backtest else backtest.get("sharpe")),
                "mdd": _fmt_pct(None if not backtest else backtest.get("max_drawdown")),
                "trades": "-" if not backtest else backtest.get("trades", "-"),
                "validation": _short_validation(backtest, baseline, robustness),
                "ai_review": _short_review(review),
            }
        )
    return rows


def _render_strategy_summary_table(rows: list[dict]) -> None:
    import pandas as pd

    frame = pd.DataFrame(rows)
    if frame.empty:
        st.info("暂无策略摘要。")
        return
    style = (
        frame.style.apply(
            lambda row: ["background-color: #fbfbfa" if row.name % 2 else "background-color: #ffffff"] * len(row),
            axis=1,
        )
        .set_table_styles(
            [
                {"selector": "th", "props": [("border", "0"), ("font-weight", "700")]},
                {"selector": "td", "props": [("border", "0"), ("padding", "8px 10px")]},
            ]
        )
        .hide(axis="index")
    )
    st.dataframe(style, use_container_width=True, hide_index=True)


def _render_regime_score_bars(regime: dict) -> None:
    scores = regime.get("component_scores") or {}
    labels = {
        "passive_beta": "Passive Beta",
        "directional_momentum": "Directional Momentum",
        "trend_following": "Trend Following",
        "range_harvesting": "Range / Grid",
        "defensive_cash": "Defensive Cash",
    }
    if not scores:
        st.info("No component scores available.")
        return
    st.caption("这是 baseline 反推的要素评分，不是确定性 regime 标签。")
    for key, score in sorted(scores.items(), key=lambda item: -item[1]):
        left, right = st.columns([0.75, 0.25])
        left.write(labels.get(key, key.replace("_", " ").title()))
        right.write(f"{score:.1f}")
        st.progress(max(0.0, min(1.0, float(score) / 100)))
    findings = regime.get("findings") or []
    if findings:
        st.caption(findings[0])


def _tasks_for_scope(tasks: list[dict], *, thesis_id: str | None, strategy_id: str | None) -> list[dict]:
    scoped = []
    for task in tasks:
        if strategy_id and task.get("strategy_id") == strategy_id:
            scoped.append(task)
        elif thesis_id and task.get("thesis_id") == thesis_id:
            scoped.append(task)
    return scoped


def _render_harness_progress(tasks: list[dict]) -> None:
    if not tasks:
        st.info("Harness 暂无近期任务。")
        return
    status_counts: dict[str, int] = {}
    for task in tasks:
        status = task.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    cols = st.columns(min(3, max(1, len(status_counts))))
    for col, (status, count) in zip(cols, sorted(status_counts.items())):
        col.metric(status.replace("_", " ").title(), count)
    for task in tasks[:8]:
        status = task.get("status", "unknown")
        task_type = task.get("task_type", "task")
        priority = float(task.get("priority_score") or 0)
        label = f"{_status_symbol(status)} {task_type.replace('_', ' ')}"
        if task.get("approval_required"):
            st.warning(label)
        elif status in {"completed", "approved"}:
            st.success(label)
        elif status in {"blocked", "rejected"}:
            st.error(label)
        else:
            st.info(label)
        st.progress(max(0.0, min(1.0, priority / 100)))
        st.caption(task.get("hypothesis", "")[:180])


def _status_symbol(status: str) -> str:
    return {
        "running": "▶",
        "completed": "✓",
        "approved": "✓",
        "blocked": "!",
        "rejected": "!",
        "proposed": "•",
    }.get(status, "•")


def _short_validation(backtest: dict | None, baseline: dict | None, robustness: dict | None) -> str:
    if robustness:
        return "robust ok" if robustness.get("passed") else "robust weak"
    if baseline:
        return "beats baseline" if baseline.get("outperformed_best_baseline") else "baseline fail"
    if backtest:
        return str(backtest.get("status", "backtested"))
    return "pending"


def _short_review(review: dict | None) -> str:
    if not review:
        return "pending"
    maturity = review.get("maturity_score") or {}
    blockers = maturity.get("blockers") or []
    if blockers:
        return "has blockers"
    stage = maturity.get("stage")
    if stage:
        return str(stage)
    score = maturity.get("overall_score")
    return "reviewed" if score is None else f"{score:.0f}/100"


def _fmt_pct(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "-"


def _fmt_num(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


@st.cache_data(ttl=300)
def _build_dashboard_baseline_regime() -> tuple[dict | None, dict | None, str | None]:
    try:
        candles_by_cell = _load_dashboard_candles()
        board = build_strategy_family_baseline_board(candles_by_cell)
        regime = build_baseline_implied_regime_report(board)
        return board.model_dump(mode="json"), regime.model_dump(mode="json"), None
    except Exception as exc:
        return None, None, f"Baseline regime scan unavailable: {exc}"


def _load_dashboard_candles():
    data_dir = Path(os.getenv("DASHBOARD_BASELINE_DATA_DIR", "freqtrade_user_data/data/binance/futures"))
    symbols = _env_list("DASHBOARD_BASELINE_SYMBOLS") or ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    timeframes = _env_list("DASHBOARD_BASELINE_TIMEFRAMES") or ["1h"]
    max_candles = int(os.getenv("DASHBOARD_BASELINE_MAX_CANDLES", "20000"))
    candles_by_cell = {}
    for symbol in symbols:
        for timeframe in timeframes:
            path = data_dir / f"{_freqtrade_symbol(symbol)}-{timeframe}-futures.feather"
            if not path.exists():
                continue
            candles = load_freqtrade_ohlcv(path, symbol, timeframe)
            if max_candles > 0 and len(candles) > max_candles:
                candles = candles[-max_candles:]
            candles_by_cell[(symbol, timeframe)] = candles
    if not candles_by_cell:
        raise ValueError(f"No OHLCV files found under {data_dir}.")
    return candles_by_cell


def _freqtrade_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


def _render_compact_validation_card(title: str, record: dict | None) -> None:
    if not record:
        st.info(f"{title}: no record")
        return
    passed = record.get("passed")
    if passed is True:
        st.success(f"{title}: passed")
    elif passed is False:
        st.warning(f"{title}: not passed")
    else:
        st.info(f"{title}: recorded")
    metrics = {
        key: record.get(key)
        for key in [
            "events_with_orderflow",
            "confirmation_rate",
            "pass_rate",
            "probability_of_loss",
            "sampled_trade_count",
        ]
        if key in record
    }
    if metrics:
        st.json(metrics)


def _human_assist_snapshot(
    *,
    board: dict | None,
    regime: dict | None,
    latest_orderflow: dict | None,
    latest_review_session: dict | None,
    latest_tasks: list[dict],
) -> dict:
    score = 0
    findings = []
    if board and board.get("rows"):
        score += 25
        findings.append({"level": "good", "message": "Generic baselines are available for strategy pressure-testing."})
    else:
        findings.append({"level": "warn", "message": "Baseline board is missing, so strategy claims lack a reference yardstick."})
    if regime and regime.get("regime_label"):
        score += 20
        findings.append({"level": "good", "message": f"Baseline-implied regime: {regime['regime_label']}."})
    if latest_orderflow and latest_orderflow.get("events_with_orderflow", 0) > 0:
        score += 20
        findings.append(
            {
                "level": "good",
                "message": f"Orderflow validation has {latest_orderflow.get('events_with_orderflow', 0)} overlapping event(s).",
            }
        )
    else:
        findings.append({"level": "warn", "message": "Orderflow validation has not yet overlapped enough events."})
    if latest_review_session:
        score += 20
        findings.append({"level": "good", "message": "AI ReviewSession exists and can drive follow-up questioning."})
    else:
        findings.append({"level": "info", "message": "No ReviewSession is available for the latest research state."})
    if latest_tasks:
        score += 15
        findings.append({"level": "good", "message": f"Harness has generated {len(latest_tasks)} recent task(s)."})
    else:
        findings.append({"level": "info", "message": "Harness task backlog is empty."})
    return {
        "score": min(100, score),
        "baseline_pressure": "available" if board and board.get("rows") else "missing",
        "review_depth": "available" if latest_review_session else "missing",
        "next_step_clarity": "available" if latest_tasks else "thin",
        "findings": findings,
    }


def _render_strategy_family_validation_followups(engine, thesis_id: str) -> None:
    universe_reports = _records_where_payload_field(engine, "failed_breakout_universe_reports", "thesis_id", thesis_id)
    if not universe_reports:
        return
    rendered = False
    for universe in universe_reports:
        source_id = universe.get("report_id")
        if not source_id:
            continue
        walk_forward_reports = _records_where_payload_field(
            engine,
            "strategy_family_walk_forward_reports",
            "source_universe_report_id",
            source_id,
        )
        monte_carlo_reports = _records_where_payload_field(
            engine,
            "strategy_family_monte_carlo_reports",
            "source_universe_report_id",
            source_id,
        )
        orderflow_reports = _records_where_payload_field(
            engine,
            "strategy_family_orderflow_acceptance_reports",
            "source_universe_report_id",
            source_id,
        )
        if not walk_forward_reports and not monte_carlo_reports and not orderflow_reports:
            continue
        if not rendered:
            st.write("**Strategy Family Validation Follow-ups**")
            rendered = True
        with st.expander(f"Validation follow-ups for {source_id}", expanded=False):
            for report in walk_forward_reports:
                st.metric("Walk-forward pass rate", f"{report.get('pass_rate', 0):.1%}")
                if report.get("passed"):
                    st.success("Walk-forward passed")
                else:
                    st.warning("Walk-forward did not pass")
                st.json(report)
            for report in monte_carlo_reports:
                st.metric("MC probability of loss", f"{report.get('probability_of_loss', 0):.1%}")
                if report.get("requires_human_confirmation"):
                    st.warning("Monte Carlo requires human confirmation")
                elif report.get("passed"):
                    st.success("Monte Carlo passed")
                else:
                    st.warning("Monte Carlo did not pass")
                st.json(report)
            for report in orderflow_reports:
                st.metric("Orderflow confirmation rate", f"{report.get('confirmation_rate', 0):.1%}")
                if report.get("passed"):
                    st.success("Orderflow acceptance passed")
                else:
                    st.warning("Orderflow acceptance did not pass")
                st.json(report)


def _render_single_payload(engine, table_name: str, field: str, value: str, title: str) -> None:
    records = _records_where_payload_field(engine, table_name, field, value)
    if not records:
        return
    st.write(f"**{title}**")
    for record in records:
        status = record.get("status") or record.get("approved")
        if status in {"failed", False}:
            st.warning(f"{title} status: {status}")
        elif status in {"passed", True}:
            st.success(f"{title} status: {status}")
        st.json(record)


def _render_related_payloads(engine, table_name: str, field: str, value: str, title: str) -> None:
    records = _records_where_payload_field(engine, table_name, field, value)
    if not records:
        return
    st.write(f"**{title}**")
    for record in records:
        st.json(record)


def render_orderflow_health(engine, database_url: str) -> None:
    st.subheader("Orderflow Collector Health")
    symbols = _env_list("ORDERFLOW_HEALTH_SYMBOLS") or _env_list("ORDERFLOW_SYMBOLS") or [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
    ]
    report = build_orderflow_health_report(
        QuantRepository(database_url),
        symbols=symbols,
        interval=os.getenv("ORDERFLOW_BAR_INTERVAL", "1m"),
        trading_mode=os.getenv("ORDERFLOW_TRADING_MODE", "futures"),
        max_staleness_seconds=int(os.getenv("ORDERFLOW_MAX_STALENESS_SECONDS", "600")),
        state_path=os.getenv("ORDERFLOW_STATE_PATH", "/app/logs/orderflow_collector_state.json"),
    )
    if report["status"] == "ok":
        st.success("Orderflow collector is fresh.")
    elif report["status"] == "warn":
        st.warning("Orderflow collector has warnings.")
    else:
        st.error("Orderflow collector is stale or missing data.")
    st.caption(f"Generated at: `{report['generated_at']}`")

    for item in report["symbols"]:
        columns = st.columns([1.2, 0.8, 0.8, 0.8, 2])
        columns[0].write(f"**{item['symbol']}**")
        columns[1].write(item["status"].upper())
        columns[2].metric("Lag", "n/a" if item["lag_seconds"] is None else f"{item['lag_seconds']}s")
        columns[3].metric("Recent bars", item["recent_bar_count"])
        columns[4].caption(item["message"])
        with st.expander(f"{item['symbol']} collector details"):
            st.json(item)

    inspector = inspect(engine)
    if "orderflow_bars" not in inspector.get_table_names():
        st.info("No structured `orderflow_bars` table found yet.")
        return
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                select symbol, interval, open_time, close_time, created_at
                from orderflow_bars
                order by created_at desc
                limit 20
                """
            )
        ).fetchall()
    st.write("### Recent Orderflow Rows")
    st.dataframe([dict(row._mapping) for row in rows], use_container_width=True)


def _env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def render_dashboard_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2rem; }
        .qod-app-header {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 6px;
        }
        .qod-app-mark {
            width: 48px;
            height: 48px;
            border-radius: 14px;
            box-shadow: 0 10px 26px rgba(23, 32, 42, 0.12);
        }
        .qod-app-title {
            font-size: 34px;
            line-height: 1.1;
            font-weight: 760;
            color: #17202a;
        }
        .qod-app-subtitle {
            color: #596579;
            font-size: 14px;
            margin-top: 4px;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e3e6ec;
            border-radius: 8px;
            padding: 12px 14px;
        }
        div[data-testid="stAlert"] {
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    page_icon = DASHBOARD_ICON_PATH if DASHBOARD_ICON_PATH.exists() else "/assets/quantodyssey-mark.svg"
    st.set_page_config(page_title="Quant Odyssey", page_icon=page_icon, layout="wide")
    render_dashboard_styles()
    st.markdown(
        """
        <div class="qod-app-header">
          <img class="qod-app-mark" src="/assets/quantodyssey-mark.svg" alt="" />
          <div>
            <div class="qod-app-title">Quant Odyssey Personal Dashboard</div>
            <div class="qod-app-subtitle">
              <a href="/" target="_self">公开主页</a> · 左侧导航，中间策略判断，右侧系统行为，下方随时提问。
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    engine, database_url = connect_database()
    st.caption(f"Database: `{database_url}`")

    tabs = st.tabs(
        [
            "Research Workbench",
            "Run Pipeline",
            "Run Detail",
            "Signals",
            "Regimes",
            "Data Quality",
            "Research Theses",
            "Pre-Reviews",
            "Research Design",
            "Event Episodes",
            "Asset Index",
            "Strategy Family WF",
            "Strategy Family MC",
            "Orderflow Acceptance",
            "Strategy Registry",
            "Experiments",
            "Experiment Queue",
            "Baselines",
            "Robustness",
            "Cross Symbol",
            "Real Validation",
            "Backtests",
            "Monte Carlo",
            "Paper Trading",
            "Paper Plans",
            "Reviews",
            "Negative Results",
            "Risk Alerts",
            "Resource Budgets",
            "Human Approval",
            "Orderflow Health",
            "Metric Audit",
            "System Status",
        ]
    )
    table_by_tab = {
        "Signals": "signals",
        "Regimes": "market_regime_snapshots",
        "Data Quality": "data_quality_reports",
        "Research Theses": "research_theses",
        "Pre-Reviews": "thesis_pre_reviews",
        "Research Design": "research_design_drafts",
        "Event Episodes": "event_episodes",
        "Asset Index": "research_asset_index",
        "Strategy Family WF": "strategy_family_walk_forward_reports",
        "Strategy Family MC": "strategy_family_monte_carlo_reports",
        "Orderflow Acceptance": "strategy_family_orderflow_acceptance_reports",
        "Strategy Registry": "strategy_registry",
        "Experiments": "experiment_manifests",
        "Experiment Queue": "experiment_queue",
        "Baselines": "baseline_comparisons",
        "Robustness": "robustness_reports",
        "Cross Symbol": "cross_symbol_validations",
        "Real Validation": "real_backtest_validation_suites",
        "Backtests": "backtests",
        "Monte Carlo": "monte_carlo_backtests",
        "Paper Trading": "paper_trading_reports",
        "Paper Plans": "paper_trading_plans",
        "Reviews": "reviews",
        "Negative Results": "negative_result_cases",
        "Risk Alerts": "portfolio_risk_reports",
        "Resource Budgets": "resource_budget_reports",
        "Human Approval": "workflow_runs",
    }

    with tabs[0]:
        render_research_workbench(engine, database_url)

    with tabs[1]:
        render_research_pipeline(engine, database_url)

    with tabs[2]:
        render_research_run_detail(engine)

    for tab, label in zip(tabs[3 : 3 + len(table_by_tab)], table_by_tab):
        table = table_by_tab[label]
        with tab:
            st.subheader(label)
            payloads = recent_payloads(engine, table)
            if not payloads:
                st.info(f"No `{table}` records found yet.")
            for payload in payloads:
                st.json(payload)

    with tabs[-3]:
        render_orderflow_health(engine, database_url)

    with tabs[-2]:
        render_metric_audit_registry()

    with tabs[-1]:
        st.subheader("System Status")
        report = run_health_checks()
        status_label = report.status.upper()
        if report.status == "ok":
            st.success(f"Overall status: {status_label}")
        elif report.status == "warn":
            st.warning(f"Overall status: {status_label}")
        else:
            st.error(f"Overall status: {status_label}")
        st.caption(f"Generated at: `{report.generated_at}`")

        for check in report.checks:
            columns = st.columns([1.2, 0.8, 3])
            columns[0].write(f"**{check.name}**")
            columns[1].write(check.status.upper())
            latency = "" if check.latency_ms is None else f" ({check.latency_ms} ms)"
            columns[2].write(f"{check.message}{latency}")
            if check.details:
                with st.expander(f"{check.name} details"):
                    st.json(check.details)

    render_global_ai_assistant(engine)


if __name__ == "__main__":
    main()
