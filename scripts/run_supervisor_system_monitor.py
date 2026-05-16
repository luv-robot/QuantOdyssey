from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import SupervisorFlagKind, SupervisorFlagSeverity, SupervisorReport  # noqa: E402
from app.services.operations import (  # noqa: E402
    delivery_results_to_dict,
    run_health_checks,
    send_supervisor_alert,
)
from app.services.supervisor import build_supervisor_report  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run system health checks and persist a SupervisorReport.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    parser.add_argument("--state-path", default=os.getenv("SUPERVISOR_ALERT_STATE_PATH", ".qo/supervisor_alert_state.json"))
    parser.add_argument("--notify", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--alert-on-warn", action=argparse.BooleanOptionalAction, default=_truthy(os.getenv("SUPERVISOR_ALERT_ON_WARN", "")))
    parser.add_argument("--repeat-minutes", type=int, default=int(os.getenv("SUPERVISOR_ALERT_REPEAT_MINUTES", "120")))
    parser.add_argument("--json", action="store_true", help="Print full monitor result JSON.")
    args = parser.parse_args()

    repository = QuantRepository(args.database_url)
    health_report = run_health_checks()
    report = build_supervisor_report(
        review_sessions=repository.query_review_sessions(limit=25),
        research_tasks=repository.query_research_tasks(limit=75),
        research_findings=repository.query_research_findings(limit=75),
        health_report=health_report,
    )
    repository.save_supervisor_report(report)

    should_alert = args.notify and _should_alert(report, alert_on_warn=args.alert_on_warn)
    notification_results = []
    if should_alert and _should_send(report, Path(args.state_path), repeat_minutes=args.repeat_minutes):
        notification_results = send_supervisor_alert(report, health_report=health_report)
        _write_alert_state(report, Path(args.state_path))

    result = {
        "supervisor_report": report.model_dump(mode="json"),
        "health_report": health_report.to_dict(),
        "notification_results": delivery_results_to_dict(notification_results),
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Supervisor System Monitor: {report.status.value}")
        print(report.summary)
        print(f"health_status: {health_report.status}")
        if notification_results:
            for delivery in notification_results:
                print(f"- notification {delivery.channel}: {delivery.status} {delivery.message}")
        for flag in report.flags[:10]:
            print(f"- {flag.severity.value.upper()} {flag.kind.value}: {flag.title}")
    return 0


def _should_alert(report: SupervisorReport, *, alert_on_warn: bool) -> bool:
    if any(flag.severity == SupervisorFlagSeverity.CRITICAL for flag in report.flags):
        return True
    return alert_on_warn and any(_is_system_flag(flag.kind) for flag in report.flags)


def _is_system_flag(kind: SupervisorFlagKind) -> bool:
    return kind in {
        SupervisorFlagKind.SYSTEM_HEALTH_FAILURE,
        SupervisorFlagKind.AUTOMATION_FAILURE,
        SupervisorFlagKind.NOTIFICATION_FAILURE,
    }


def _should_send(report: SupervisorReport, state_path: Path, *, repeat_minutes: int) -> bool:
    fingerprint = _alert_fingerprint(report)
    if not state_path.exists():
        return True
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True
    if state.get("fingerprint") != fingerprint:
        return True
    last_sent_at = float(state.get("sent_at", 0))
    return (time.time() - last_sent_at) >= repeat_minutes * 60


def _write_alert_state(report: SupervisorReport, state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "fingerprint": _alert_fingerprint(report),
                "sent_at": time.time(),
                "report_id": report.report_id,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _alert_fingerprint(report: SupervisorReport) -> str:
    parts = [
        f"{flag.kind.value}:{flag.severity.value}:{flag.title}:{','.join(flag.evidence_refs)}"
        for flag in report.flags
        if flag.severity in {SupervisorFlagSeverity.CRITICAL, SupervisorFlagSeverity.WARN}
    ]
    return "|".join(sorted(parts))


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
