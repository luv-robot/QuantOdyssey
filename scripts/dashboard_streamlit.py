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
    BacktestCostModel,
    MarketSignal,
    MonteCarloBacktestConfig,
    PreReviewStatus,
    ResearchThesis,
    ThesisStatus,
)
from app.services.operations import run_health_checks  # noqa: E402
from app.services.agent_eval import build_builtin_agent_eval_cases, run_agent_eval_suite  # noqa: E402
from app.services.assistant import build_dashboard_assistant_answer, build_dashboard_context  # noqa: E402
from app.services.harness import build_baseline_implied_regime_report, build_strategy_family_baseline_board  # noqa: E402
from app.services.market_data import build_orderflow_health_report, load_freqtrade_ohlcv  # noqa: E402
from app.services.metrics import performance_metric_registry  # noqa: E402
from app.services.researcher import (  # noqa: E402
    build_research_design_draft,
    build_thesis_data_contract,
    build_thesis_seed_signal,
    build_thesis_pre_review,
    draft_thesis_fields_from_notes,
)
from app.services.supervisor import build_supervisor_report, supervisor_chat_answer  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


DEFAULT_DB_URL = "sqlite+pysqlite:///market_data.sqlite3"
DASHBOARD_ICON_PATH = ROOT / "public" / "assets" / "quantodyssey-mark.svg"
KEY_TABLES = [
    "research_theses",
    "thesis_pre_reviews",
    "research_design_drafts",
    "thesis_data_contracts",
    "event_episodes",
    "research_asset_index",
    "research_findings",
    "research_tasks",
    "thesis_inbox",
    "research_harness_cycles",
    "agent_eval_runs",
    "supervisor_reports",
    "public_thesis_cards",
    "public_strategy_cards",
    "strategy_catalog_items",
    "strategy_catalog_reports",
    "factor_formula_items",
    "factor_formula_catalog_reports",
    "prompt_logs",
    "model_response_logs",
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
    signal_options = {
        "Auto: build data context from thesis": None,
        **{
        f"{item['signal_id']} | {item['symbol']} | rank {item['rank_score']} | {item['created_at']}": item
        for item in signals
        },
    }
    with st.form("research_pipeline_form"):
        research_notes = st.text_area(
            "Research command / thesis notes",
            placeholder=(
                "Paste a raw idea or tell Odyssey what you want to test. "
                "Example: Test daily BTC RSI divergence, long-only, OHLCV only, must define stoploss."
            ),
            height=180,
        )
        selected_label = st.selectbox("Data context", list(signal_options))
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
        with st.expander("Cost model", expanded=False):
            st.caption("Defaults apply to this submitted strategy run; adjust only when you have a reason.")
            cost_left, cost_mid, cost_right, funding_col = st.columns(4)
            fee_rate = cost_left.number_input(
                "Fee / side",
                min_value=0.0,
                max_value=0.1,
                value=0.0005,
                step=0.0001,
                format="%.5f",
            )
            slippage_bps = cost_mid.number_input("Slippage bps / side", min_value=0.0, value=2.0, step=0.5)
            spread_bps = cost_right.number_input("Spread bps / side", min_value=0.0, value=0.0, step=0.5)
            funding_rate_8h = funding_col.number_input(
                "Funding / 8h",
                min_value=-0.1,
                max_value=0.1,
                value=0.0,
                step=0.0001,
                format="%.5f",
            )
            funding_source = st.text_input("Funding source", value="not_available")
        approve_expensive = st.checkbox("Approve expensive Monte Carlo if threshold is exceeded")
        pre_review_only = st.form_submit_button("Preview Research Design")
        submitted = st.form_submit_button("Run Research Pipeline")

    if not (pre_review_only or submitted):
        return
    draft = draft_thesis_fields_from_notes(research_notes)
    title_value = title.strip() or draft.get("title", "").strip()
    observation_value = market_observation.strip() or draft.get("market_observation", "").strip()
    hypothesis_value = hypothesis.strip() or draft.get("hypothesis", "").strip()
    trade_logic_value = trade_logic.strip() or draft.get("trade_logic", "").strip()
    expected_regimes_value = expected_regimes.strip() or draft.get("expected_regimes", "").strip()
    invalidation_value = invalidation_conditions.strip() or draft.get("invalidation_conditions", "").strip()
    constraints_value = "\n".join(
        item
        for item in [constraints.strip(), draft.get("constraints", "").strip()]
        if item
    )
    if not all([title_value, observation_value, hypothesis_value, trade_logic_value]):
        st.error("Title, observation, hypothesis, and trade logic are required.")
        return

    thesis = ResearchThesis(
        thesis_id=f"thesis_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}",
        title=title_value,
        status=ThesisStatus.READY_FOR_IMPLEMENTATION,
        market_observation=observation_value,
        hypothesis=hypothesis_value,
        trade_logic=trade_logic_value,
        expected_regimes=_lines(expected_regimes_value, ["unspecified"]),
        invalidation_conditions=_lines(invalidation_value, ["not specified"]),
        linked_signal_ids=[],
        constraints=_lines(constraints_value, []),
    )
    selected_payload = signal_options[selected_label]
    selected_signal = None if selected_payload is None else MarketSignal.model_validate(selected_payload)
    data_contract = build_thesis_data_contract(thesis, selected_signal)
    signal = selected_signal
    if signal is None or not data_contract.can_run:
        signal = build_thesis_seed_signal(thesis, source_signal=selected_signal)
        data_contract = build_thesis_data_contract(thesis, signal).model_copy(
            update={
                "warnings": list(
                    dict.fromkeys(
                        [
                            *data_contract.mismatches,
                            *data_contract.warnings,
                            "Using a thesis-seed data context so the run follows the thesis data requirements.",
                        ]
                    )
                ),
                "recommended_action": (
                    "Confirm historical data exists for this thesis-seed timeframe before trusting real backtests."
                ),
            }
        )
    thesis = thesis.model_copy(update={"linked_signal_ids": [signal.signal_id]})
    repository = QuantRepository(database_url)
    pre_review = build_thesis_pre_review(thesis)
    research_design = build_research_design_draft(thesis, pre_review)
    repository.save_signal(signal)
    repository.save_research_thesis(thesis)
    repository.save_thesis_data_contract(data_contract)
    repository.save_thesis_pre_review(pre_review)
    repository.save_research_design_draft(research_design)

    st.write("### Data Contract")
    if data_contract.warnings:
        st.warning("Data context adjusted: " + " ".join(data_contract.warnings))
    st.json(data_contract.model_dump(mode="json"))
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
            cost_model=BacktestCostModel(
                fee_rate=float(fee_rate),
                slippage_bps=float(slippage_bps),
                spread_bps=float(spread_bps),
                funding_rate_8h=float(funding_rate_8h),
                funding_source=funding_source.strip() or "not_available",
            ),
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
    research_findings = recent_records(engine, "research_findings", limit=200)
    failed_breakout_universes = recent_records(engine, "failed_breakout_universe_reports", limit=100)
    event_definition_universes = recent_records(engine, "event_definition_universe_reports", limit=100)
    walk_forward_reports = recent_records(engine, "strategy_family_walk_forward_reports", limit=80)
    family_monte_carlo_reports = recent_records(engine, "strategy_family_monte_carlo_reports", limit=80)
    strategy_monte_carlo_reports = recent_records(engine, "monte_carlo_backtests", limit=120)
    orderflow_acceptance_reports = recent_records(engine, "strategy_family_orderflow_acceptance_reports", limit=80)
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
        upper_frame = st.container()
        lower_frame = st.container()
        with upper_frame:
            st.write("### 市场 Regime 要素评分")
            if error:
                st.warning(error)
            elif regime:
                _render_regime_score_bars(regime)
                _render_baseline_direction_snapshot(board)
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

        with lower_frame:
            render_assistant_workspace(selected_thesis=selected_thesis, selected_strategy=selected_strategy)

    with right_col:
        st.write("### 系统行为")
        scoped_tasks = _tasks_for_scope(
            latest_tasks,
            thesis_id=None if not selected_thesis else selected_thesis.get("thesis_id"),
            strategy_id=None if not selected_strategy else selected_strategy.get("strategy_id"),
        )
        _render_harness_progress(scoped_tasks or latest_tasks[:8])

        st.write("### 研究进展时间线")
        timeline_items = _build_research_timeline(
            findings=research_findings,
            walk_forward_reports=walk_forward_reports,
            family_monte_carlo_reports=family_monte_carlo_reports,
            strategy_monte_carlo_reports=strategy_monte_carlo_reports,
            orderflow_acceptance_reports=orderflow_acceptance_reports,
            universe_reports=[*failed_breakout_universes, *event_definition_universes],
            strategies=strategies,
            thesis_id=None if not selected_thesis else selected_thesis.get("thesis_id"),
            strategy_id=None if not selected_strategy else selected_strategy.get("strategy_id"),
            limit=10,
        )
        _render_research_timeline(timeline_items)

        st.write("### 快速入口")
        st.info("Run Detail：查看策略证据链")
        st.info("Metric Audit：查看指标公式")
        st.info("System Status：检查数据服务")


def render_assistant_workspace(selected_thesis: dict | None = None, selected_strategy: dict | None = None) -> None:
    st.markdown('<div class="qod-assistant-workspace">', unsafe_allow_html=True)
    st.write("### Assistant Workspace")
    thesis_label = "未选择 thesis" if not selected_thesis else selected_thesis.get("title", selected_thesis.get("thesis_id"))
    strategy_label = (
        "未选择策略"
        if not selected_strategy
        else selected_strategy.get("name", selected_strategy.get("strategy_id"))
    )
    st.caption(f"当前上下文：{thesis_label} · {strategy_label}")
    messages = st.session_state.get("qod_assistant_messages", [])
    if not messages:
        st.info("底部输入框会一直常驻。长回答会显示在这里，不挤占底部输入区。")
    else:
        for message in messages[-8:]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    st.markdown("</div>", unsafe_allow_html=True)


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


def render_agent_quality_console(engine, database_url: str) -> None:
    st.subheader("Agent Quality Console")
    st.caption("Admin-only quality control for Harness, Reviewer, Researcher, and Supervisor behavior.")
    repository = QuantRepository(database_url)

    latest_eval_run = _latest_agent_eval_run(repository)
    latest_report = _latest_supervisor_report(repository)

    left, right = st.columns([0.7, 0.3])
    with left:
        st.write("**Supervisor Status**")
        if latest_report is None:
            st.info("No SupervisorReport exists yet. Run a smoke check to create the first report.")
        else:
            _render_supervisor_status(latest_report.model_dump(mode="json"))
    with right:
        if st.button("Run Agent Eval Smoke", type="primary"):
            cases = build_builtin_agent_eval_cases()
            responses = {
                case.case_id: " ".join([*case.expected_terms, "evidence discipline followed"])
                for case in cases
            }
            eval_run = run_agent_eval_suite(responses, cases=cases)
            report = build_supervisor_report(
                agent_eval_run=eval_run,
                review_sessions=repository.query_review_sessions(limit=25),
                research_tasks=repository.query_research_tasks(limit=50),
                research_findings=repository.query_research_findings(limit=50),
            )
            repository.save_agent_eval_run(eval_run)
            repository.save_supervisor_report(report)
            st.success("Agent Eval smoke completed and SupervisorReport saved.")
            latest_eval_run = eval_run
            latest_report = report

    if latest_eval_run is not None:
        st.write("### Agent Eval")
        eval_payload = latest_eval_run.model_dump(mode="json")
        scores = eval_payload.get("aggregate_scores") or {}
        score_cols = st.columns(max(1, min(4, len(scores))))
        for col, (name, score) in zip(score_cols, scores.items()):
            col.metric(name.replace("_", " ").title(), f"{score:.1f}")
        for result in eval_payload.get("results", []):
            label = f"{result.get('case_id')} · {result.get('target_agent')} · score {result.get('score')}"
            if result.get("passed"):
                st.success(label)
            else:
                st.error(label)
            with st.expander(f"Eval details: {result.get('case_id')}", expanded=False):
                st.json(result)

    if latest_report is not None:
        report_payload = latest_report.model_dump(mode="json")
        st.write("### Supervisor Flags")
        flags = report_payload.get("flags") or []
        if not flags:
            st.success("No quality-control flags.")
        for flag in flags[:20]:
            _render_supervisor_flag(flag)

        st.write("### Supervisor Chat")
        with st.form("supervisor_chat_form"):
            question = st.text_input(
                "Ask Supervisor",
                placeholder="例如：最近 AI Review 有没有误判？哪些任务有预算风险？",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Ask")
        if submitted and question.strip():
            answer = supervisor_chat_answer(
                question.strip(),
                report=latest_report,
                agent_eval_run=latest_eval_run,
                research_tasks=repository.query_research_tasks(limit=50),
                review_sessions=repository.query_review_sessions(limit=25),
            )
            st.info(answer)


def _latest_agent_eval_run(repository: QuantRepository):
    runs = repository.query_agent_eval_runs(limit=1)
    return runs[0] if runs else None


def _latest_supervisor_report(repository: QuantRepository):
    reports = repository.query_supervisor_reports(limit=1)
    return reports[0] if reports else None


def _render_supervisor_status(report: dict) -> None:
    status = report.get("status", "unknown")
    if status == "ok":
        st.success(report.get("summary", "Supervisor status is ok."))
    elif status == "critical":
        st.error(report.get("summary", "Supervisor status is critical."))
    else:
        st.warning(report.get("summary", "Supervisor status has warnings."))
    st.caption(f"report_id: `{report.get('report_id')}`")
    actions = report.get("recommended_next_actions") or []
    if actions:
        st.write("**Recommended next actions**")
        for action in actions:
            st.write(f"- {action}")


def _render_supervisor_flag(flag: dict) -> None:
    severity = flag.get("severity")
    label = f"{flag.get('kind')} · {flag.get('title')}"
    if severity == "critical":
        st.error(label)
    elif severity == "warn":
        st.warning(label)
    else:
        st.info(label)
    st.caption(flag.get("summary", ""))
    st.caption(f"Recommended: {flag.get('recommended_action', '')}")
    refs = flag.get("evidence_refs") or []
    if refs:
        st.caption("Evidence: " + ", ".join(f"`{ref}`" for ref in refs[:6]))


def render_strategy_catalog(engine) -> None:
    st.subheader("Strategy Catalog")
    reports = recent_records(engine, "strategy_catalog_reports", limit=5)
    items = recent_records(engine, "strategy_catalog_items", limit=200)
    factor_reports = recent_records(engine, "factor_formula_catalog_reports", limit=5)
    factors = recent_records(engine, "factor_formula_items", limit=200)
    if not reports and not items and not factor_reports and not factors:
        st.info("No catalog records found yet. Import Lean metadata and seed factor formulas first.")
        st.code(
            "python scripts/import_lean_strategy_catalog.py --language python --max-files 100 --save-to-db\n"
            "python scripts/seed_factor_formula_catalog.py --save-to-db",
            language="bash",
        )
        return

    if reports:
        st.write("**Lean Strategy Samples**")
        latest = reports[0]
        columns = st.columns(4)
        columns[0].metric("Catalog Items", latest.get("item_count", 0))
        columns[1].metric("Scanned Files", latest.get("total_files_scanned", 0))
        columns[2].metric(
            "Baseline Candidates",
            (latest.get("suggested_role_counts") or {}).get("baseline_candidate", 0),
        )
        columns[3].metric("Low Difficulty", (latest.get("difficulty_counts") or {}).get("low", 0))
        for finding in latest.get("findings", []):
            st.caption(finding)
        with st.expander("Latest catalog report"):
            st.json(latest)

    if items:
        rows = [
            {
                "name": item.get("name"),
                "language": item.get("language"),
                "family": item.get("strategy_family"),
                "difficulty": item.get("migration_difficulty"),
                "roles": ", ".join(item.get("suggested_roles") or []),
                "assets": ", ".join(item.get("asset_classes") or []),
                "data": ", ".join(item.get("data_requirements") or []),
                "source_path": item.get("source_path"),
            }
            for item in items
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        with st.expander("Catalog item payloads"):
            for item in items[:25]:
                st.json(item)

    if factor_reports:
        st.write("**WorldQuant-Style Factor Templates**")
        latest_factor_report = factor_reports[0]
        columns = st.columns(4)
        columns[0].metric("Factor Templates", latest_factor_report.get("total_items", 0))
        columns[1].metric("Baseline Candidates", latest_factor_report.get("baseline_candidate_count", 0))
        columns[2].metric(
            "Portable OHLCV",
            (latest_factor_report.get("implementation_status_counts") or {}).get("portable_ohlcv", 0),
        )
        columns[3].metric(
            "Cross-Sectional",
            (latest_factor_report.get("scope_counts") or {}).get("cross_sectional_universe", 0),
        )
        for finding in latest_factor_report.get("findings", []):
            st.caption(finding)
        with st.expander("Latest factor catalog report"):
            st.json(latest_factor_report)

    if factors:
        factor_rows = [
            {
                "name": item.get("name"),
                "family": item.get("factor_family"),
                "scope": item.get("evaluation_scope"),
                "status": item.get("implementation_status"),
                "data_level": item.get("data_sufficiency_level"),
                "fields": ", ".join(item.get("required_fields") or []),
                "roles": ", ".join(item.get("baseline_roles") or []),
                "formula": item.get("formula_expression"),
            }
            for item in factors
        ]
        st.dataframe(factor_rows, use_container_width=True, hide_index=True)
        with st.expander("Factor formula payloads"):
            for item in factors[:25]:
                st.json(item)


def render_global_ai_assistant(engine, database_url: str) -> None:
    st.markdown(
        f"""
        <div class="qod-assistant-dock">
          <span class="qod-assistant-plus">+</span>
          <span class="qod-assistant-label">Quant Odyssey Assistant</span>
          <span class="qod-assistant-pill">DeepSeek V4 Pro</span>
          <span class="qod-assistant-hint">已有数据会优先引导到内部页面</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "qod_assistant_messages" not in st.session_state:
        st.session_state.qod_assistant_messages = []

    question = st.chat_input(
        "问 Quant Odyssey，或直接粘贴 thesis：策略为什么被拒？现在 regime 如何？提交 thesis 要补什么？",
        key="qod_global_chat_input",
    )
    if not question or not question.strip():
        return

    st.session_state.qod_assistant_messages.append({"role": "user", "content": question.strip()})
    context = _build_assistant_context(engine)
    repository = QuantRepository(database_url)
    available_signals = [
        MarketSignal.model_validate(payload)
        for payload in recent_records(engine, "signals", limit=25)
    ]
    result = build_dashboard_assistant_answer(
        question.strip(),
        context=context,
        repository=repository,
        available_signals=available_signals,
    )
    answer = result.answer
    st.session_state.qod_assistant_messages.append({"role": "assistant", "content": answer})
    st.rerun()


def _build_assistant_context(engine) -> dict:
    theses = recent_records(engine, "research_theses", limit=5)
    tasks = recent_records(engine, "research_tasks", limit=8)
    reviews = recent_records(engine, "review_sessions", limit=5)
    board, regime, _ = _build_dashboard_baseline_regime()
    catalog_summary = {
        "lean_items": _table_count(engine, "strategy_catalog_items"),
        "lean_reports": _table_count(engine, "strategy_catalog_reports"),
        "factor_items": _table_count(engine, "factor_formula_items"),
        "factor_reports": _table_count(engine, "factor_formula_catalog_reports"),
    }
    return build_dashboard_context(
        theses=theses,
        tasks=tasks,
        regime=regime,
        baseline_board=board,
        latest_reviews=reviews,
        catalog_summary=catalog_summary,
    )


def _table_count(engine, table_name: str) -> int:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return 0
    with engine.connect() as connection:
        return int(connection.execute(text(f"select count(*) from {table_name}")).scalar() or 0)


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


def _render_baseline_direction_snapshot(board: dict | None) -> None:
    if not board or not board.get("rows"):
        return
    rows = sorted(
        board.get("rows") or [],
        key=lambda item: float(item.get("total_return") or 0),
        reverse=True,
    )
    st.write("**Baseline Direction Check**")
    cost_model = board.get("cost_model") or {}
    if cost_model:
        st.caption(
            "Cost model: "
            f"fee={_fmt_pct(cost_model.get('fee_rate'))}, "
            f"slippage={_fmt_num(cost_model.get('slippage_bps'))} bps, "
            f"spread={_fmt_num(cost_model.get('spread_bps'))} bps, "
            f"funding_8h={_fmt_pct(cost_model.get('funding_rate_8h'))}."
        )
    table_rows = []
    for row in rows[:8]:
        table_rows.append(
            {
                "baseline": row.get("display_name") or row.get("strategy_family"),
                "group": row.get("benchmark_group", "-"),
                "direction": row.get("direction_bias", "-"),
                "window": board.get("timeframe_scope", "-"),
                "net": _fmt_pct(row.get("total_return")),
                "gross": _fmt_pct(row.get("gross_return")),
                "cost": _fmt_pct(row.get("cost_drag")),
                "pf": _fmt_num(row.get("profit_factor")),
                "trades": row.get("trades", "-"),
                "periods": row.get("portfolio_period_count", "-"),
            }
        )
    st.dataframe(table_rows, use_container_width=True, hide_index=True)


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


def _build_research_timeline(
    *,
    findings: list[dict],
    walk_forward_reports: list[dict],
    family_monte_carlo_reports: list[dict],
    strategy_monte_carlo_reports: list[dict],
    orderflow_acceptance_reports: list[dict],
    universe_reports: list[dict],
    strategies: list[dict],
    thesis_id: str | None,
    strategy_id: str | None,
    limit: int = 10,
) -> list[dict]:
    universe_by_id = {
        record.get("report_id"): record
        for record in universe_reports
        if record.get("report_id")
    }
    strategy_to_thesis = {
        record.get("strategy_id"): record.get("thesis_id")
        for record in strategies
        if record.get("strategy_id")
    }
    items: list[dict] = []

    for finding in findings:
        if not _timeline_scope_matches(finding, thesis_id=thesis_id, strategy_id=strategy_id):
            continue
        kind = finding.get("finding_type", "finding")
        severity = finding.get("severity", "low")
        observations = finding.get("observations") or []
        items.append(
            _timeline_item(
                created_at=finding.get("created_at"),
                kind=_label_from_slug(kind),
                title=f"Finding · {_label_from_slug(kind)}",
                level=_severity_level(severity),
                summary=finding.get("summary") or "Harness recorded a research finding.",
                metrics=[f"severity={severity}", *_compact_list(observations, 2)],
                refs=finding.get("evidence_refs") or [],
            )
        )

    for report in walk_forward_reports:
        source = universe_by_id.get(report.get("source_universe_report_id"), {})
        if not _timeline_scope_matches(source, thesis_id=thesis_id, strategy_id=None):
            continue
        passed = bool(report.get("passed"))
        pass_rate = float(report.get("pass_rate") or 0)
        items.append(
            _timeline_item(
                created_at=report.get("created_at"),
                kind="Walk-forward",
                title=f"Walk-forward · {report.get('strategy_family', 'strategy family')}",
                level="good" if passed else "warn",
                summary=_first_or_default(
                    report.get("findings"),
                    "Walk-forward validation completed.",
                ),
                metrics=[
                    f"pass_rate={pass_rate:.1%}",
                    f"windows={report.get('completed_windows', 0)}",
                    f"passed={report.get('passed_windows', 0)}",
                    f"min_trades={report.get('min_trades_per_window', '-')}",
                ],
                refs=[
                    f"strategy_family_walk_forward_report:{report.get('report_id')}",
                    f"source_universe_report:{report.get('source_universe_report_id')}",
                ],
            )
        )

    for report in family_monte_carlo_reports:
        source = universe_by_id.get(report.get("source_universe_report_id"), {})
        if not _timeline_scope_matches(source, thesis_id=thesis_id, strategy_id=None):
            continue
        passed = bool(report.get("passed"))
        level = "good" if passed else "warn"
        if report.get("requires_human_confirmation") and not report.get("approved_to_run"):
            level = "high"
        items.append(
            _timeline_item(
                created_at=report.get("created_at"),
                kind="Monte Carlo",
                title=f"Family MC · {report.get('strategy_family', 'strategy family')}",
                level=level,
                summary=_first_or_default(report.get("findings"), "Strategy-family Monte Carlo completed."),
                metrics=[
                    f"p_loss={_fmt_pct_compact(report.get('probability_of_loss'))}",
                    f"p05={_fmt_pct_compact(report.get('p05_return'))}",
                    f"sample={report.get('sampled_trade_count', 0)}",
                    f"sims={report.get('simulations', 0)}",
                ],
                refs=[
                    f"strategy_family_monte_carlo_report:{report.get('report_id')}",
                    f"source_universe_report:{report.get('source_universe_report_id')}",
                ],
            )
        )

    for report in orderflow_acceptance_reports:
        source = universe_by_id.get(report.get("source_universe_report_id"), {})
        if not _timeline_scope_matches(source, thesis_id=thesis_id, strategy_id=None):
            continue
        passed = bool(report.get("passed"))
        items.append(
            _timeline_item(
                created_at=report.get("created_at"),
                kind="Orderflow",
                title=f"Orderflow · {report.get('strategy_family', 'strategy family')}",
                level="good" if passed else "warn",
                summary=_first_or_default(report.get("findings"), "Orderflow acceptance validation completed."),
                metrics=[
                    f"confirm={_fmt_pct_compact(report.get('confirmation_rate'))}",
                    f"conflict={_fmt_pct_compact(report.get('conflict_rate'))}",
                    f"events={report.get('events_with_orderflow', 0)}",
                ],
                refs=[
                    f"strategy_family_orderflow_acceptance_report:{report.get('report_id')}",
                    f"source_universe_report:{report.get('source_universe_report_id')}",
                ],
            )
        )

    for report in strategy_monte_carlo_reports:
        report_strategy_id = report.get("strategy_id")
        report_thesis_id = strategy_to_thesis.get(report_strategy_id)
        if strategy_id and report_strategy_id != strategy_id:
            continue
        if thesis_id and report_thesis_id != thesis_id and not strategy_id:
            continue
        if thesis_id and strategy_id and report_strategy_id != strategy_id and report_thesis_id != thesis_id:
            continue
        level = "good"
        if report.get("requires_human_confirmation") and not report.get("approved_to_run"):
            level = "high"
        elif float(report.get("probability_of_loss") or 0) >= 0.45 or float(report.get("p05_return") or 0) < -0.1:
            level = "warn"
        items.append(
            _timeline_item(
                created_at=report.get("created_at"),
                kind="Monte Carlo",
                title=f"Strategy MC · {report_strategy_id or 'strategy'}",
                level=level,
                summary="Strategy-level Monte Carlo path-risk test completed.",
                metrics=[
                    f"p_loss={_fmt_pct_compact(report.get('probability_of_loss'))}",
                    f"median={_fmt_pct_compact(report.get('median_return'))}",
                    f"p05={_fmt_pct_compact(report.get('p05_return'))}",
                    f"horizon={report.get('horizon_trades', 0)}",
                ],
                refs=[
                    f"monte_carlo_backtest:{report.get('report_id')}",
                    f"backtest:{report.get('source_backtest_id')}",
                ],
            )
        )

    return sorted(items, key=lambda item: item["_sort_at"], reverse=True)[:limit]


def _render_research_timeline(items: list[dict]) -> None:
    if not items:
        st.info("暂无自动研究结论。Harness 会在定时任务中继续扫描队列。")
        return
    attention_count = sum(1 for item in items if item["level"] in {"warn", "high"})
    cols = st.columns(2)
    cols[0].metric("Recent Events", len(items))
    cols[1].metric("Need Attention", attention_count)
    for item in items:
        headline = f"{item['icon']} {item['title']}"
        message = f"{headline}\n\n{item['summary']}"
        if item["level"] == "high":
            st.error(message)
        elif item["level"] == "warn":
            st.warning(message)
        elif item["level"] == "good":
            st.success(message)
        else:
            st.info(message)
        meta = " · ".join([item["display_at"], item["kind"], *item["metrics"]])
        st.caption(meta)
        refs = [ref for ref in item.get("refs", []) if ref and not ref.endswith(":None")]
        if refs:
            with st.expander("artifact refs", expanded=False):
                for ref in refs[:6]:
                    st.code(ref, language=None)


def _timeline_item(
    *,
    created_at,
    kind: str,
    title: str,
    level: str,
    summary: str,
    metrics: list[str],
    refs: list[str],
) -> dict:
    parsed = _parse_datetime(created_at)
    return {
        "_sort_at": parsed or datetime.min,
        "display_at": "-" if parsed is None else parsed.strftime("%m-%d %H:%M"),
        "kind": kind,
        "title": title,
        "level": level,
        "icon": {"high": "!", "warn": "!", "good": "✓", "info": "•"}.get(level, "•"),
        "summary": summary,
        "metrics": [item for item in metrics if item],
        "refs": refs,
    }


def _timeline_scope_matches(record: dict, *, thesis_id: str | None, strategy_id: str | None) -> bool:
    if strategy_id and record.get("strategy_id") == strategy_id:
        return True
    if thesis_id and record.get("thesis_id") == thesis_id:
        return True
    if strategy_id or thesis_id:
        return False
    return True


def _severity_level(severity: str) -> str:
    return {"high": "high", "medium": "warn", "low": "info"}.get(str(severity).lower(), "info")


def _label_from_slug(value: str) -> str:
    return str(value).replace("_", " ").replace("-", " ").title()


def _compact_list(values: list, limit: int) -> list[str]:
    return [str(item)[:110] for item in values[:limit]]


def _first_or_default(values, default: str) -> str:
    if isinstance(values, list) and values:
        return str(values[0])
    return default


def _fmt_pct_compact(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "-"


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


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
        .qod-assistant-workspace {
            margin-top: 22px;
            padding: 14px 16px 18px 16px;
            border-top: 1px solid #e4e7ee;
            background: linear-gradient(180deg, #ffffff 0%, #fbfcfd 100%);
        }
        .qod-assistant-dock {
            position: sticky;
            bottom: 0;
            z-index: 20;
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 18px;
            padding: 10px 14px;
            border: 1px solid #dfe3ea;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.96);
            box-shadow: 0 10px 28px rgba(24, 36, 54, 0.14);
            color: #1f2937;
        }
        .qod-assistant-plus {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid #d6dbe5;
            font-weight: 700;
        }
        .qod-assistant-label {
            font-weight: 700;
        }
        .qod-assistant-pill {
            padding: 3px 8px;
            border-radius: 999px;
            background: #eef3ff;
            color: #3054a6;
            font-size: 12px;
            font-weight: 700;
        }
        .qod-assistant-hint {
            color: #687386;
            font-size: 13px;
        }
        div[data-testid="stChatFloatingInputContainer"] {
            border-top: 1px solid #e2e6ef;
            background: rgba(255, 255, 255, 0.98);
            padding-bottom: 0.85rem;
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
            "Agent Quality",
            "Strategy Catalog",
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

    agent_quality_index = 3 + len(table_by_tab)
    with tabs[agent_quality_index]:
        render_agent_quality_console(engine, database_url)

    with tabs[agent_quality_index + 1]:
        render_strategy_catalog(engine)

    with tabs[agent_quality_index + 2]:
        render_orderflow_health(engine, database_url)

    with tabs[agent_quality_index + 3]:
        render_metric_audit_registry()

    with tabs[agent_quality_index + 4]:
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
