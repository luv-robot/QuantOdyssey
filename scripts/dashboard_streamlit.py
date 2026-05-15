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
    st.subheader("Research Workbench")
    recent_theses = recent_records(engine, "research_theses", limit=8)
    latest_orderflow = _latest_record(engine, "strategy_family_orderflow_acceptance_reports")
    latest_review_session = _latest_record(engine, "review_sessions")
    latest_walk_forward = _latest_record(engine, "strategy_family_walk_forward_reports")
    latest_monte_carlo = _latest_record(engine, "strategy_family_monte_carlo_reports")
    latest_tasks = recent_records(engine, "research_tasks", limit=20)

    columns = st.columns(5)
    columns[0].metric("Theses", _metric_count(engine, "research_theses"))
    columns[1].metric("Review Sessions", _metric_count(engine, "review_sessions"))
    columns[2].metric("Open Tasks", _open_task_count(latest_tasks))
    columns[3].metric("Orderflow Bars", _metric_count(engine, "orderflow_bars"))
    columns[4].metric(
        "OF Events",
        0 if latest_orderflow is None else latest_orderflow.get("events_with_orderflow", 0),
    )

    queue_col, evidence_col, action_col = st.columns([0.85, 1.2, 0.95])
    with queue_col:
        st.write("### Research Queue")
        if recent_theses:
            for thesis in recent_theses[:5]:
                st.write(f"**{thesis.get('title', thesis.get('thesis_id'))}**")
                st.caption(f"{thesis.get('status')} | {thesis.get('thesis_id')}")
        else:
            st.info("No thesis records yet.")
        st.write("### Harness Backlog")
        if latest_tasks:
            for task in latest_tasks[:6]:
                status = task.get("status")
                task_type = task.get("task_type")
                priority = task.get("priority_score")
                if task.get("approval_required"):
                    st.warning(f"{task_type} | priority {priority} | {status}")
                else:
                    st.info(f"{task_type} | priority {priority} | {status}")
        else:
            st.info("No recent harness tasks.")

    with evidence_col:
        st.write("### Baseline-Implied Regime")
        board, regime, error = _build_dashboard_baseline_regime()
        if error:
            st.warning(error)
        elif board is not None and regime is not None:
            regime_cols = st.columns(3)
            regime_cols[0].metric("Regime", regime["regime_label"])
            regime_cols[1].metric("Confidence", f"{regime['confidence']:.1%}")
            regime_cols[2].metric("Best Baseline", board.get("best_family") or "n/a")
            st.dataframe(
                [
                    {
                        "baseline": row["strategy_family"],
                        "return": row["total_return"],
                        "profit_factor": row["profit_factor"],
                        "sharpe": row["sharpe"],
                        "max_drawdown": row["max_drawdown"],
                        "trades": row["trades"],
                        "positive_cells": row["positive_cell_count"],
                        "tested_cells": row["tested_cell_count"],
                    }
                    for row in board["rows"]
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.write("**Regime Components**")
            st.dataframe(
                [
                    {"component": name, "score": score}
                    for name, score in regime.get("component_scores", {}).items()
                ],
                use_container_width=True,
                hide_index=True,
            )
            for finding in regime.get("findings", []):
                st.caption(finding)
        else:
            st.info("No baseline regime data available.")

    with action_col:
        st.write("### Evidence Court")
        _render_compact_validation_card("Orderflow Acceptance", latest_orderflow)
        _render_compact_validation_card("Walk Forward", latest_walk_forward)
        _render_compact_validation_card("Monte Carlo", latest_monte_carlo)
        st.write("### AI Review")
        if latest_review_session:
            maturity = latest_review_session.get("maturity_score") or {}
            st.metric("Maturity Score", f"{maturity.get('overall_score', 0):.2f}")
            evidence_against = latest_review_session.get("evidence_against") or []
            blind_spots = latest_review_session.get("blind_spots") or []
            questions = latest_review_session.get("ai_questions") or []
            experiments = latest_review_session.get("next_experiments") or []
            if evidence_against:
                st.write("**Evidence Against**")
                for claim in evidence_against[:3]:
                    st.warning(claim.get("statement", "evidence against"))
            if blind_spots:
                st.write("**Blind Spots**")
                for claim in blind_spots[:3]:
                    st.info(claim.get("statement", "blind spot"))
            if questions:
                st.write("**AI Questions**")
                for question in questions[:3]:
                    st.caption(question.get("question", "question"))
            if experiments:
                st.write("**Next Experiments**")
                for experiment in experiments[:3]:
                    st.caption(experiment)
        else:
            st.info("No ReviewSession records yet.")

    st.write("### Human-Assist Penetration Snapshot")
    snapshot = _human_assist_snapshot(
        board=board if "board" in locals() else None,
        regime=regime if "regime" in locals() else None,
        latest_orderflow=latest_orderflow,
        latest_review_session=latest_review_session,
        latest_tasks=latest_tasks,
    )
    score_cols = st.columns(4)
    score_cols[0].metric("Helpfulness", f"{snapshot['score']:.0f}/100")
    score_cols[1].metric("Baseline Pressure", snapshot["baseline_pressure"])
    score_cols[2].metric("Review Depth", snapshot["review_depth"])
    score_cols[3].metric("Next-Step Clarity", snapshot["next_step_clarity"])
    for item in snapshot["findings"]:
        if item["level"] == "good":
            st.success(item["message"])
        elif item["level"] == "warn":
            st.warning(item["message"])
        else:
            st.info(item["message"])


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


def main() -> None:
    st.set_page_config(page_title="Quant Odyssey", layout="wide")
    st.title("Quant Odyssey Research Workbench")

    engine, database_url = connect_database()
    st.caption(f"Database: `{database_url}`")

    summary_tables = [
        "research_theses",
        "review_sessions",
        "research_tasks",
        "orderflow_bars",
        "backtests",
        "reviews",
    ]
    columns = st.columns(len(summary_tables))
    for column, table in zip(columns, summary_tables):
        value = table_count(engine, table)
        column.metric(table.replace("_", " ").title(), "n/a" if value is None else value)

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


if __name__ == "__main__":
    main()
