from __future__ import annotations

from typing import Optional

from app.models import RiskAuditResult, StrategyManifest
from app.services.risk_auditor import audit_strategy_code
from app.storage import QuantRepository


def run_risk_audit_flow(
    strategy_code: str,
    manifest: StrategyManifest,
    repository: Optional[QuantRepository] = None,
) -> RiskAuditResult:
    result = audit_strategy_code(strategy_code, manifest)
    if repository is not None:
        repository.save_risk_audit(result)
    return result
