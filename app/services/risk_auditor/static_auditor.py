from __future__ import annotations

import ast
import re

from app.models import RiskAuditResult, RiskFinding, RiskSeverity, StrategyManifest


FORBIDDEN_KEYWORDS: dict[str, tuple[RiskSeverity, str]] = {
    "martingale": (RiskSeverity.CRITICAL, "Martingale-style logic is forbidden."),
    "adjust_trade_position": (RiskSeverity.HIGH, "DCA or position adjustment requires review."),
    "requests.": (RiskSeverity.HIGH, "External network calls are forbidden in strategies."),
    "urllib": (RiskSeverity.HIGH, "External network calls are forbidden in strategies."),
    "eval(": (RiskSeverity.CRITICAL, "Dynamic code execution is forbidden."),
    "exec(": (RiskSeverity.CRITICAL, "Dynamic code execution is forbidden."),
    ".shift(-": (RiskSeverity.CRITICAL, "Negative shift may indicate lookahead bias."),
}


def _has_stoploss(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "stoploss":
                    return True
    return False


def _leverage_findings(code: str, max_leverage: int) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    for match in re.finditer(r"leverage\s*=\s*([0-9]+(?:\.[0-9]+)?)", code):
        leverage = float(match.group(1))
        if leverage > max_leverage:
            findings.append(
                RiskFinding(
                    rule_id="LEVERAGE_LIMIT",
                    severity=RiskSeverity.HIGH,
                    message=f"Strategy leverage {leverage:g} exceeds max {max_leverage}.",
                )
            )
    return findings


def audit_strategy_code(
    strategy_code: str,
    manifest: StrategyManifest,
    max_leverage: int = 1,
) -> RiskAuditResult:
    findings: list[RiskFinding] = []

    try:
        tree = ast.parse(strategy_code)
    except SyntaxError as exc:
        return RiskAuditResult(
            strategy_id=manifest.strategy_id,
            approved=False,
            findings=[
                RiskFinding(
                    rule_id="PYTHON_SYNTAX",
                    severity=RiskSeverity.CRITICAL,
                    message=f"Strategy code is not valid Python: {exc.msg}.",
                )
            ],
        )

    if not _has_stoploss(tree):
        findings.append(
            RiskFinding(
                rule_id="STOPLOSS_REQUIRED",
                severity=RiskSeverity.HIGH,
                message="Strategy does not define stoploss.",
            )
        )

    lowered = strategy_code.lower()
    for keyword, (severity, message) in FORBIDDEN_KEYWORDS.items():
        if keyword in lowered:
            findings.append(RiskFinding(rule_id=keyword.upper(), severity=severity, message=message))

    findings.extend(_leverage_findings(lowered, max_leverage=max_leverage))

    return RiskAuditResult(
        strategy_id=manifest.strategy_id,
        approved=not findings,
        findings=findings,
    )
