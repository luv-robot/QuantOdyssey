from __future__ import annotations

from uuid import uuid4

from app.models import (
    AgentEvalRun,
    ResearchFinding,
    ResearchFindingSeverity,
    ResearchTask,
    ResearchTaskStatus,
    ReviewSession,
    SupervisorFlag,
    SupervisorFlagKind,
    SupervisorFlagSeverity,
    SupervisorReport,
    SupervisorStatus,
)


def build_supervisor_report(
    *,
    agent_eval_run: AgentEvalRun | None = None,
    review_sessions: list[ReviewSession] | None = None,
    research_tasks: list[ResearchTask] | None = None,
    research_findings: list[ResearchFinding] | None = None,
    health_report=None,
) -> SupervisorReport:
    review_sessions = review_sessions or []
    research_tasks = research_tasks or []
    research_findings = research_findings or []

    flags: list[SupervisorFlag] = []
    if agent_eval_run is not None:
        flags.extend(_flags_from_agent_eval(agent_eval_run))
    flags.extend(_flags_from_review_sessions(review_sessions))
    flags.extend(_flags_from_research_tasks(research_tasks))
    flags.extend(_flags_from_findings(research_findings))
    if health_report is not None:
        flags.extend(_flags_from_health_report(health_report))

    status = _status_from_flags(flags)
    return SupervisorReport(
        report_id=f"supervisor_report_{uuid4().hex[:8]}",
        source_agent_eval_run_id=None if agent_eval_run is None else agent_eval_run.run_id,
        status=status,
        summary=_summary(status, flags),
        aggregate_scores={} if agent_eval_run is None else agent_eval_run.aggregate_scores,
        flags=flags,
        recommended_next_actions=_recommended_next_actions(flags),
    )


def supervisor_chat_answer(
    question: str,
    *,
    report: SupervisorReport | None = None,
    agent_eval_run: AgentEvalRun | None = None,
    research_tasks: list[ResearchTask] | None = None,
    review_sessions: list[ReviewSession] | None = None,
    health_report=None,
) -> str:
    lower = question.lower()
    research_tasks = research_tasks or []
    review_sessions = review_sessions or []
    report = report or build_supervisor_report(
        agent_eval_run=agent_eval_run,
        review_sessions=review_sessions,
        research_tasks=research_tasks,
        health_report=health_report,
    )

    if any(key in lower for key in ["health", "健康", "系统", "报错", "error", "异常", "告警"]):
        system_flags = [
            flag
            for flag in report.flags
            if flag.kind
            in {
                SupervisorFlagKind.SYSTEM_HEALTH_FAILURE,
                SupervisorFlagKind.AUTOMATION_FAILURE,
                SupervisorFlagKind.NOTIFICATION_FAILURE,
            }
        ]
        if not system_flags:
            return "当前 Supervisor 没有发现系统级健康告警。可以继续查看 Health Checks 或最近的 SupervisorReport。"
        top = system_flags[0]
        return f"当前有 {len(system_flags)} 个系统级告警。优先看：{top.title}。建议：{top.recommended_action}"

    if any(key in lower for key in ["fail", "失败", "退化", "eval", "评测"]):
        failed = [
            flag
            for flag in report.flags
            if flag.kind == SupervisorFlagKind.AGENT_EVAL_FAILURE
        ]
        if not failed:
            return "最近的 Agent Eval 没有发现失败项。可以查看 Agent Quality Console 的 case results 和 aggregate scores。"
        return (
            f"最近有 {len(failed)} 个 Agent Eval failure。优先看："
            f"{failed[0].title}。建议动作：{failed[0].recommended_action}"
        )
    if any(key in lower for key in ["budget", "预算", "循环", "runaway", "重复"]):
        risky = [
            task
            for task in research_tasks
            if task.approval_required or task.status in {ResearchTaskStatus.BLOCKED, ResearchTaskStatus.REJECTED}
        ]
        if not risky:
            return "近期 ResearchTask 没有明显预算或循环风险。昂贵任务会被 Harness Budget Guardrail 标记为人工批准。"
        return f"近期有 {len(risky)} 个任务需要预算关注。优先看 `{risky[0].task_id}`。"
    if any(key in lower for key in ["review", "误判", "证据", "blind", "blocker"]):
        risky_reviews = [session for session in review_sessions if session.evidence_against or session.blind_spots]
        if not risky_reviews:
            return "最近 ReviewSession 没有明显 evidence_against 或 blind_spots。仍建议抽检最新 ReviewSession 的 scorecard。"
        return (
            f"最近有 {len(risky_reviews)} 个 ReviewSession 带有反证或盲点。"
            f"优先看 `{risky_reviews[0].session_id}`，它可作为人工复核入口。"
        )
    if report.flags:
        top = report.flags[0]
        return f"当前 Supervisor 状态是 `{report.status.value}`。最高优先级 flag：{top.title}。建议：{top.recommended_action}"
    return f"当前 Supervisor 状态是 `{report.status.value}`，没有需要立即处理的质量 flag。"


def _flags_from_agent_eval(run: AgentEvalRun) -> list[SupervisorFlag]:
    flags = []
    for result in run.results:
        if result.passed and result.score >= 70:
            continue
        flags.append(
            SupervisorFlag(
                flag_id=f"flag_agent_eval_{result.case_id}_{uuid4().hex[:8]}",
                kind=SupervisorFlagKind.AGENT_EVAL_FAILURE,
                severity=SupervisorFlagSeverity.CRITICAL if result.score < 50 else SupervisorFlagSeverity.WARN,
                title=f"Agent eval failed: {result.case_id}",
                summary="; ".join(result.findings),
                recommended_action="Inspect the responsible prompt/skill/model route before trusting similar automated reviews.",
                evidence_refs=[f"agent_eval_run:{run.run_id}", f"agent_eval_case:{result.case_id}"],
                linked_agent_eval_run_id=run.run_id,
            )
        )
    return flags


def _flags_from_review_sessions(review_sessions: list[ReviewSession]) -> list[SupervisorFlag]:
    flags = []
    for session in review_sessions:
        blockers = session.maturity_score.blockers
        if session.blind_spots or blockers:
            flags.append(
                SupervisorFlag(
                    flag_id=f"flag_review_{session.session_id}_{uuid4().hex[:8]}",
                    kind=SupervisorFlagKind.REVIEW_SESSION_RISK,
                    severity=SupervisorFlagSeverity.WARN,
                    title=f"ReviewSession needs audit: {session.strategy_id}",
                    summary=f"{len(session.blind_spots)} blind spot(s), {len(blockers)} blocker(s).",
                    recommended_action="Open the ReviewSession and verify evidence gaps before allowing follow-up automation.",
                    evidence_refs=[f"review_session:{session.session_id}", f"strategy:{session.strategy_id}"],
                    linked_review_session_id=session.session_id,
                )
            )
    return flags


def _flags_from_research_tasks(tasks: list[ResearchTask]) -> list[SupervisorFlag]:
    flags = []
    for task in tasks:
        if not task.approval_required and task.status != ResearchTaskStatus.BLOCKED:
            continue
        severity = SupervisorFlagSeverity.CRITICAL if task.status == ResearchTaskStatus.BLOCKED else SupervisorFlagSeverity.WARN
        flags.append(
            SupervisorFlag(
                flag_id=f"flag_task_{task.task_id}_{uuid4().hex[:8]}",
                kind=SupervisorFlagKind.TASK_BUDGET_RISK,
                severity=severity,
                title=f"Task requires supervisor attention: {task.task_type.value}",
                summary=(
                    f"Task `{task.task_id}` has status `{task.status.value}`, "
                    f"estimated_cost={task.estimated_cost}, approval_required={task.approval_required}."
                ),
                recommended_action="Approve, reject, or narrow the experiment before the Harness spends more budget.",
                evidence_refs=[f"research_task:{task.task_id}"],
                linked_task_id=task.task_id,
            )
        )
    return flags


def _flags_from_findings(findings: list[ResearchFinding]) -> list[SupervisorFlag]:
    flags = []
    for finding in findings:
        if finding.severity != ResearchFindingSeverity.HIGH and not finding.evidence_gaps:
            continue
        flags.append(
            SupervisorFlag(
                flag_id=f"flag_finding_{finding.finding_id}_{uuid4().hex[:8]}",
                kind=SupervisorFlagKind.DATA_GAP if finding.evidence_gaps else SupervisorFlagKind.SYSTEM_NOTE,
                severity=SupervisorFlagSeverity.WARN,
                title=f"Finding needs follow-up: {finding.finding_type}",
                summary=finding.summary,
                recommended_action="Convert the finding into a bounded ResearchTask or explicitly archive the gap.",
                evidence_refs=[f"research_finding:{finding.finding_id}", *finding.evidence_refs],
            )
        )
    return flags


def _flags_from_health_report(health_report) -> list[SupervisorFlag]:
    flags = []
    for check in getattr(health_report, "checks", []):
        status = getattr(check, "status", "ok")
        if status == "ok":
            continue
        name = getattr(check, "name", "unknown")
        message = getattr(check, "message", "Health check did not provide a message.")
        severity = SupervisorFlagSeverity.CRITICAL if status == "fail" else SupervisorFlagSeverity.WARN
        kind = (
            SupervisorFlagKind.AUTOMATION_FAILURE
            if any(token in name for token in ["prefect", "n8n", "collector", "scheduler"])
            else SupervisorFlagKind.SYSTEM_HEALTH_FAILURE
        )
        flags.append(
            SupervisorFlag(
                flag_id=f"flag_health_{name}_{uuid4().hex[:8]}",
                kind=kind,
                severity=severity,
                title=f"System health check {status}: {name}",
                summary=message,
                recommended_action=_health_recommended_action(name, status),
                evidence_refs=[f"health_check:{name}", f"health_status:{status}"],
            )
        )
    return flags


def _status_from_flags(flags: list[SupervisorFlag]) -> SupervisorStatus:
    if any(flag.severity == SupervisorFlagSeverity.CRITICAL for flag in flags):
        return SupervisorStatus.CRITICAL
    if any(flag.severity == SupervisorFlagSeverity.WARN for flag in flags):
        return SupervisorStatus.WARN
    return SupervisorStatus.OK


def _summary(status: SupervisorStatus, flags: list[SupervisorFlag]) -> str:
    if not flags:
        return "Supervisor found no current quality-control flags."
    return f"Supervisor status is {status.value}; {len(flags)} quality-control flag(s) require review."


def _recommended_next_actions(flags: list[SupervisorFlag]) -> list[str]:
    if not flags:
        return ["Continue scheduled agent evals and sample ReviewSession audits."]
    actions = []
    for flag in flags[:5]:
        actions.append(flag.recommended_action)
    return list(dict.fromkeys(actions))


def _health_recommended_action(name: str, status: str) -> str:
    if name == "database":
        return "Check Postgres container health, connection credentials, and recent migration/schema errors."
    if name == "orderflow_collector":
        return "Inspect orderflow collector logs, Binance connectivity, and latest orderflow_bars freshness."
    if name in {"prefect", "n8n", "qdrant"}:
        return f"Check the {name} container, local endpoint, and reverse-proxy/network path before relying on automation."
    if name == "disk":
        return "Free disk space or move bulky data/logs before running larger backtests or data backfills."
    if name == "webhook_secret":
        return "Set a strong N8N_WEBHOOK_SECRET before accepting external webhook traffic."
    return f"Inspect `{name}` health details and pause high-cost automation if status remains `{status}`."
