from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import MarketSignal, ModelResponseLog, PromptLog, ResearchThesis, ThesisStatus
from app.services.assistant.deepseek import ChatCompletionResult, DeepSeekChatClient
from app.services.harness import build_thesis_intake_harness_cycle
from app.services.researcher import (
    build_research_design_draft,
    build_thesis_data_contract,
    build_thesis_pre_review,
    build_thesis_seed_signal,
    draft_thesis_fields_from_notes,
    select_compatible_signal,
)
from app.storage import QuantRepository


@dataclass(frozen=True)
class DashboardAssistantResult:
    answer: str
    provider: str
    model: str
    used_llm: bool
    prompt_id: str
    response_id: str
    error: str | None = None
    action: str | None = None
    artifacts: dict[str, Any] | None = None


def build_dashboard_context(
    *,
    theses: list[dict[str, Any]] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    regime: dict[str, Any] | None = None,
    baseline_board: dict[str, Any] | None = None,
    latest_reviews: list[dict[str, Any]] | None = None,
    catalog_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "recent_theses": _truncate_records(theses or [], keep_keys=["thesis_id", "title", "status", "created_at"]),
        "recent_tasks": _truncate_records(tasks or [], keep_keys=["task_id", "task_type", "status", "priority_score"]),
        "regime": regime or {},
        "baseline_board": baseline_board or {},
        "latest_reviews": _truncate_records(
            latest_reviews or [],
            keep_keys=["session_id", "thesis_id", "strategy_id", "scorecard", "maturity_score"],
        ),
        "catalog_summary": catalog_summary or {},
        "available_pages": [
            "Research Workbench",
            "Run Pipeline",
            "Run Detail",
            "Strategy Catalog",
            "Agent Quality",
            "Metric Audit",
            "System Status",
        ],
    }


def build_dashboard_assistant_answer(
    question: str,
    *,
    context: dict[str, Any],
    repository: QuantRepository | None = None,
    client: Any | None = None,
    available_signals: list[MarketSignal] | None = None,
    scratchpad_base_dir: Path | str | None = None,
) -> DashboardAssistantResult:
    client = client or DeepSeekChatClient()
    provider = getattr(client, "provider", "deepseek")
    model = getattr(client, "model", "deepseek-v4-pro")
    prompt_id = f"prompt_dashboard_assistant_{uuid4().hex[:8]}"
    response_id = f"response_dashboard_assistant_{uuid4().hex[:8]}"
    action_result = (
        _maybe_handle_thesis_intake(
            question,
            repository=repository,
            available_signals=available_signals or [],
            scratchpad_base_dir=scratchpad_base_dir,
        )
        if repository is not None
        else None
    )
    if action_result is not None:
        provider = "quant_odyssey"
        model = "assistant_thesis_intake_v1"
    prompt_text = _prompt_text(question, context)
    prompt_log = PromptLog(
        prompt_id=prompt_id,
        agent="dashboard_assistant",
        model=model,
        prompt_version="dashboard_assistant_v1_deepseek",
        prompt_text=prompt_text,
        input_payload={"question": question, "context": context, "provider": provider},
    )
    if repository is not None:
        repository.save_prompt_log(prompt_log)

    if action_result is not None:
        completion = ChatCompletionResult(
            content=action_result["answer"],
            raw={"action": action_result["action"], "artifacts": action_result["artifacts"]},
        )
        used_llm = False
        answer = action_result["answer"]
    else:
        configured = getattr(client, "is_configured", lambda: True)()
        if configured:
            completion = client.complete(_messages(question, context))
        else:
            completion = ChatCompletionResult(
                content="",
                raw={},
                error=f"{provider} is not configured.",
            )

        used_llm = bool(completion.content and not completion.error)
        answer = completion.content if used_llm else rule_based_dashboard_answer(question, context)
        if completion.error:
            answer = f"{answer}\n\n_注：DeepSeek 暂未接通，当前使用站内规则摘要。原因：{completion.error}_"

    response_log = ModelResponseLog(
        response_id=response_id,
        prompt_id=prompt_id,
        agent="dashboard_assistant",
        model=model,
        output_payload={
            "answer": answer,
            "used_llm": used_llm,
            "provider": provider,
            "raw": completion.raw,
            "action": None if action_result is None else action_result["action"],
        },
        parsed_ok=used_llm or action_result is not None,
        error=completion.error,
    )
    if repository is not None:
        repository.save_model_response_log(response_log)

    return DashboardAssistantResult(
        answer=answer,
        provider=provider,
        model=model,
        used_llm=used_llm,
        prompt_id=prompt_id,
        response_id=response_id,
        error=completion.error,
        action=None if action_result is None else action_result["action"],
        artifacts=None if action_result is None else action_result["artifacts"],
    )


def rule_based_dashboard_answer(question: str, context: dict[str, Any]) -> str:
    lower = question.lower()
    theses = context.get("recent_theses") or []
    tasks = context.get("recent_tasks") or []
    regime = context.get("regime") or {}
    board = context.get("baseline_board") or {}
    catalog = context.get("catalog_summary") or {}
    if any(key in lower for key in ["regime", "市场", "环境", "行情"]):
        components = regime.get("component_scores", {})
        if not components:
            return "目前还没有可用的 regime 要素评分。请先看 `Research Workbench` 的市场 Regime 区域，或运行 baseline-regime scan。"
        leader = max(components.items(), key=lambda item: item[1], default=("unknown", 0))
        return (
            f"当前应看作要素评分而非确定结论。领先因子是 `{leader[0]}`，分数 {leader[1]:.1f}。"
            "请看 `Research Workbench` 中间的 Regime 要素评分；公式口径在 `Metric Audit`。"
        )
    if any(key in lower for key in ["profit factor", "pf", "公式", "指标", "drawdown", "sharpe"]):
        return (
            "指标公式已集中到 `Metric Audit`。Profit Factor = 盈利交易总收益 / 亏损交易总亏损绝对值；"
            "Sharpe 应基于周期收益序列；最大回撤来自 equity curve 峰谷。"
        )
    if any(key in lower for key in ["catalog", "lean", "worldquant", "因子", "baseline", "基线"]):
        return (
            f"`Strategy Catalog` 已有 Lean 样本 {catalog.get('lean_items', 0)} 条、"
            f"WorldQuant-style 因子模板 {catalog.get('factor_items', 0)} 条。"
            "它们是 baseline/commonness-risk/reference，不是已验证 alpha。"
        )
    if any(key in lower for key in ["策略", "strategy", "review", "为什么", "通过"]):
        latest = theses[0].get("title") if theses else "最新 thesis"
        return (
            f"请先在左侧 thesis→strategy 树选择策略；中间表只显示摘要。"
            f"要看 `{latest}` 的完整 evidence、validation summary、AI Review，请进入 `Run Detail`。"
        )
    if any(key in lower for key in ["任务", "harness", "进度", "执行"]):
        if not tasks:
            return "Harness 暂无任务。提交 thesis 或运行 pipeline 后，右侧 `系统行为` 会显示任务进度。"
        return f"当前最近有 {len(tasks)} 个 harness 任务。右侧 `系统行为` 显示执行进度；需要原始 payload 可看相关数据标签。"
    if board.get("best_family"):
        return (
            f"建议先看 `Research Workbench`：当前最佳通用 baseline 是 `{board['best_family']}`。"
            "策略细节看 `Run Detail`，计算口径看 `Metric Audit`，系统健康看 `System Status`。"
        )
    return "建议从 `Research Workbench` 开始；它把导航、策略摘要、系统行为和可追问入口放在同一页。"


def _messages(question: str, context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are Quant Odyssey's in-dashboard research assistant. "
                "Answer in concise Chinese. Be warm, rigorous, and skeptical. "
                "Use only the supplied context for factual claims about this system. "
                "Guide users to internal pages by name when existing data or pages can answer them. "
                "Never claim a strategy is live-ready; distinguish baseline, evidence, and hypothesis."
            ),
        },
        {"role": "user", "content": _prompt_text(question, context)},
    ]


def _prompt_text(question: str, context: dict[str, Any]) -> str:
    return (
        "User question:\n"
        f"{question}\n\n"
        "Dashboard context JSON:\n"
        f"{json.dumps(context, ensure_ascii=False, default=str)[:12000]}"
    )


def _truncate_records(records: list[dict[str, Any]], *, keep_keys: list[str], limit: int = 8) -> list[dict[str, Any]]:
    truncated = []
    for record in records[:limit]:
        truncated.append({key: record.get(key) for key in keep_keys if key in record})
    return truncated


def _maybe_handle_thesis_intake(
    question: str,
    *,
    repository: QuantRepository | None,
    available_signals: list[MarketSignal],
    scratchpad_base_dir: Path | str | None,
) -> dict[str, Any] | None:
    if repository is None or not _looks_like_thesis_submission(question):
        return None
    notes = _extract_thesis_notes(question)
    draft = draft_thesis_fields_from_notes(notes)
    thesis = _research_thesis_from_draft(draft, notes)
    selected_signal, selected_contract = select_compatible_signal(thesis, available_signals)
    if selected_signal is None:
        source_signal = available_signals[0] if available_signals else None
        signal = build_thesis_seed_signal(thesis, source_signal=source_signal)
        initial_contract = build_thesis_data_contract(thesis, source_signal)
        data_contract = build_thesis_data_contract(thesis, signal).model_copy(
            update={
                "warnings": list(
                    dict.fromkeys(
                        [
                            *initial_contract.mismatches,
                            *initial_contract.warnings,
                            "Assistant created a thesis-seed data context so the research flow follows the thesis timeframe/data requirements.",
                        ]
                    )
                ),
                "recommended_action": (
                    "Confirm historical data availability for this thesis-seed context before trusting real backtests."
                ),
            }
        )
    else:
        signal = selected_signal
        data_contract = selected_contract or build_thesis_data_contract(thesis, signal)

    thesis = thesis.model_copy(update={"linked_signal_ids": [signal.signal_id]})
    pre_review = build_thesis_pre_review(thesis)
    research_design = build_research_design_draft(thesis, pre_review)
    thesis_status = (
        ThesisStatus.DRAFT
        if pre_review.status.value == "needs_clarification"
        else ThesisStatus.READY_FOR_IMPLEMENTATION
    )
    thesis = thesis.model_copy(update={"status": thesis_status})
    intake = build_thesis_intake_harness_cycle(
        thesis=thesis,
        signal=signal,
        pre_review=pre_review,
        research_design=research_design,
        data_contract=data_contract,
        existing_tasks=repository.query_research_tasks(thesis_id=thesis.thesis_id, limit=20),
        scratchpad_base_dir=scratchpad_base_dir,
    )

    repository.save_signal(signal)
    repository.save_research_thesis(thesis)
    repository.save_thesis_data_contract(data_contract)
    repository.save_thesis_pre_review(pre_review)
    repository.save_research_design_draft(research_design)
    repository.save_event_episode(intake.event_episode)
    for finding in intake.findings:
        repository.save_research_finding(finding)
    for task in intake.tasks:
        repository.save_research_task(task)
    repository.save_research_harness_cycle(intake.cycle)

    artifacts = {
        "thesis_id": thesis.thesis_id,
        "signal_id": signal.signal_id,
        "data_contract_id": data_contract.contract_id,
        "pre_review_id": pre_review.pre_review_id,
        "research_design_id": research_design.design_id,
        "event_id": intake.event_episode.event_id,
        "cycle_id": intake.cycle.cycle_id,
        "task_ids": [task.task_id for task in intake.tasks],
        "scratchpad_path": None if intake.scratchpad_run is None else intake.scratchpad_run.scratchpad_path,
    }
    return {
        "action": "thesis_intake",
        "artifacts": artifacts,
        "answer": _thesis_intake_answer(
            thesis=thesis,
            signal=signal,
            pre_review=pre_review,
            research_design=research_design,
            data_contract=data_contract,
            tasks=intake.tasks,
            scratchpad_path=artifacts["scratchpad_path"],
        ),
    }


def _looks_like_thesis_submission(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 80:
        return False
    lower = stripped.lower()
    if any(term in lower for term in ["怎么提交", "如何提交", "where do i submit", "在哪个菜单"]):
        return False
    directive = any(
        term in lower
        for term in [
            "提交 thesis",
            "提交thesis",
            "新增 thesis",
            "新建 thesis",
            "保存为 thesis",
            "保存成 thesis",
            "submit thesis",
            "new thesis",
            "把下面",
            "以下是",
        ]
    )
    sectioned = stripped.startswith("#") and any(term in lower for term in ["hypothesis", "假设", "交易逻辑"])
    chinese_sections = all(term in stripped for term in ["市场观察", "假设"]) and any(
        term in stripped for term in ["交易逻辑", "入场", "出场"]
    )
    return directive or sectioned or chinese_sections


def _extract_thesis_notes(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^\s*(请)?(把下面|以下是|提交\s*thesis|新增\s*thesis|新建\s*thesis)[:：,\s]*", "", cleaned, flags=re.I)
    return cleaned.strip()


def _research_thesis_from_draft(draft: dict[str, str], notes: str) -> ResearchThesis:
    title = draft.get("title") or "Untitled Research Thesis"
    return ResearchThesis(
        thesis_id=f"thesis_assistant_{uuid4().hex[:10]}",
        title=title[:120],
        author="assistant_intake",
        status=ThesisStatus.DRAFT,
        market_observation=(draft.get("market_observation") or notes)[:1200],
        hypothesis=(draft.get("hypothesis") or notes)[:1200],
        trade_logic=(draft.get("trade_logic") or notes)[:1200],
        expected_regimes=_lines(draft.get("expected_regimes") or "unspecified"),
        invalidation_conditions=_lines(draft.get("invalidation_conditions") or "not specified"),
        constraints=_lines(draft.get("constraints") or ""),
    )


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _thesis_intake_answer(
    *,
    thesis: ResearchThesis,
    signal: MarketSignal,
    pre_review,
    research_design,
    data_contract,
    tasks,
    scratchpad_path: str | None,
) -> str:
    question_lines = [f"- {question.question}" for question in pre_review.questions[:4]]
    task_lines = [
        f"- `{task.task_type.value}` priority={task.priority_score:.0f}: {task.rationale}"
        for task in sorted(tasks, key=lambda item: item.priority_score, reverse=True)[:5]
    ]
    warning_lines = [f"- {item}" for item in [*data_contract.mismatches, *data_contract.warnings][:5]]
    return "\n".join(
        [
            f"已把这段内容保存为 thesis：`{thesis.title}`。",
            "",
            f"- thesis_id: `{thesis.thesis_id}`",
            f"- data context: `{signal.signal_id}` / `{signal.timeframe}` / `{signal.symbol}`",
            f"- inferred family: `{research_design.inferred_strategy_family.value}`",
            f"- evaluation: `{research_design.evaluation_type.value}`",
            f"- data contract: `{data_contract.status.value}`",
            f"- pre-review: `{pre_review.status.value}`，完整度 {pre_review.completeness_score:.0f}，清晰度 {pre_review.condition_clarity_score:.0f}，常见模板风险 {pre_review.commonness_risk_score:.0f}",
            "",
            "Harness 已生成第一轮研究任务：",
            *(task_lines or ["- 暂无任务。"]),
            "",
            "需要你优先回应的问题：",
            *(question_lines or ["- 暂无阻塞问题，可以进入 `Run Pipeline` 做第一轮候选生成。"]),
            "",
            "数据/口径提醒：",
            *(warning_lines or ["- 当前 data contract 未发现阻塞性错配。"]),
            "",
            f"scratchpad: `{scratchpad_path}`" if scratchpad_path else "scratchpad: 未写入",
            "",
            "下一步建议：在 `Research Workbench` 查看 thesis→strategy 树和右侧 Harness 任务；确认问题后再进 `Run Pipeline`，避免一上来就把错配数据跑成伪结论。",
        ]
    )
