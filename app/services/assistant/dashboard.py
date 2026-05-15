from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.models import ModelResponseLog, PromptLog
from app.services.assistant.deepseek import ChatCompletionResult, DeepSeekChatClient
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
) -> DashboardAssistantResult:
    client = client or DeepSeekChatClient()
    provider = getattr(client, "provider", "deepseek")
    model = getattr(client, "model", "deepseek-v4-pro")
    prompt_id = f"prompt_dashboard_assistant_{uuid4().hex[:8]}"
    response_id = f"response_dashboard_assistant_{uuid4().hex[:8]}"
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
        },
        parsed_ok=used_llm,
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
