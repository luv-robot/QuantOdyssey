from __future__ import annotations

from typing import Any

from app.models import NegativeResultCase, ResearchThesis


def build_negative_result_case(
    thesis: ResearchThesis,
    result: Any,
    selected_candidate_id: str | None,
) -> NegativeResultCase | None:
    if result.candidate.candidate_id == selected_candidate_id:
        return None
    manifest = result.candidate.manifest
    reasons: list[str] = []
    patterns: list[str] = []
    lessons: list[str] = []

    if not result.risk_audit.approved:
        reasons.append("Risk audit rejected the strategy.")
        patterns.extend(finding.pattern for finding in result.risk_audit.findings)
        lessons.append("Do not spend backtest budget on strategies rejected by static risk audit.")
    if result.backtest is not None and result.backtest.status.value == "failed":
        reasons.append(result.backtest.error or "Backtest failed.")
        patterns.append("backtest_failed")
    if result.validation is not None and not result.validation.approved:
        reasons.extend(result.validation.findings)
        patterns.append("validation_failed")
    if result.robustness_report is not None and not result.robustness_report.passed:
        reasons.extend(result.robustness_report.findings)
        patterns.append("robustness_failed")
    if not result.selected and selected_candidate_id is not None:
        reasons.append("Candidate was not selected as the best available research asset.")
        lessons.append("Compare candidates against the selected alternative before revisiting this idea.")

    if not reasons:
        return None
    return NegativeResultCase(
        case_id=f"negative_{result.candidate.candidate_id}",
        thesis_id=thesis.thesis_id,
        signal_id=manifest.signal_id,
        strategy_id=manifest.strategy_id,
        candidate_id=result.candidate.candidate_id,
        reason=" ".join(dict.fromkeys(reasons)),
        failure_patterns=list(dict.fromkeys(patterns)) or ["not_selected"],
        reusable_lessons=list(dict.fromkeys(lessons)) or ["Preserve this case for future comparison."],
        linked_artifacts={
            **({"backtest_id": result.backtest.backtest_id} if result.backtest else {}),
            **({"validation_id": result.validation.validation_id} if result.validation else {}),
            **({"robustness_report_id": result.robustness_report.report_id} if result.robustness_report else {}),
        },
    )
