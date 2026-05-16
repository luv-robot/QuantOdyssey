from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models import SupervisorReport
from app.services.operations.health import HealthReport


@dataclass(frozen=True)
class NotificationDeliveryResult:
    channel: str
    status: str
    message: str
    latency_ms: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def build_supervisor_alert_payload(
    report: SupervisorReport,
    *,
    health_report: HealthReport | None = None,
    user_email: str | None = None,
    dev_agent_channel: str | None = None,
) -> dict[str, Any]:
    """Build a stable payload for n8n, email, Feishu, Telegram, or dev-agent bridges."""

    critical_flags = [flag for flag in report.flags if flag.severity.value == "critical"]
    warn_flags = [flag for flag in report.flags if flag.severity.value == "warn"]
    return {
        "type": "supervisor_system_alert",
        "status": report.status.value,
        "summary": report.summary,
        "created_at": report.created_at.isoformat(),
        "report_id": report.report_id,
        "notify": {
            "user_email": user_email or os.getenv("SUPERVISOR_ALERT_EMAIL_TO", "luweiword@gmail.com"),
            "dev_agent_channel": dev_agent_channel
            or os.getenv("SUPERVISOR_DEV_AGENT_CHANNEL", "dashboard_supervisor_inbox"),
        },
        "dev_agent_handoff": {
            "priority": "critical" if critical_flags else "warn",
            "instruction": (
                "Inspect the latest SupervisorReport, system health checks, and linked artifacts. "
                "Fix infrastructure or automation failures before launching new high-cost research tasks."
            ),
            "evidence_refs": list(
                dict.fromkeys(ref for flag in report.flags for ref in flag.evidence_refs)
            ),
        },
        "counts": {
            "critical_flags": len(critical_flags),
            "warn_flags": len(warn_flags),
            "total_flags": len(report.flags),
        },
        "flags": [
            {
                "flag_id": flag.flag_id,
                "kind": flag.kind.value,
                "severity": flag.severity.value,
                "title": flag.title,
                "summary": flag.summary,
                "recommended_action": flag.recommended_action,
                "evidence_refs": flag.evidence_refs,
            }
            for flag in report.flags[:20]
        ],
        "recommended_next_actions": report.recommended_next_actions,
        "health_report": None if health_report is None else health_report.to_dict(),
    }


def send_supervisor_alert(
    report: SupervisorReport,
    *,
    health_report: HealthReport | None = None,
    webhook_url: str | None = None,
    dev_agent_webhook_url: str | None = None,
    user_email: str | None = None,
    timeout_seconds: int = 10,
) -> list[NotificationDeliveryResult]:
    payload = build_supervisor_alert_payload(
        report,
        health_report=health_report,
        user_email=user_email,
    )
    results: list[NotificationDeliveryResult] = []
    endpoints = [
        ("user_alert_webhook", webhook_url or os.getenv("SUPERVISOR_ALERT_WEBHOOK_URL")),
        ("dev_agent_webhook", dev_agent_webhook_url or os.getenv("SUPERVISOR_DEV_AGENT_WEBHOOK_URL")),
    ]
    for channel, endpoint in endpoints:
        if not endpoint:
            results.append(NotificationDeliveryResult(channel, "skipped", "Webhook URL is not configured."))
            continue
        results.append(_post_json(channel, endpoint, payload, timeout_seconds=timeout_seconds))
    return results


def _post_json(
    channel: str,
    url: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: int,
) -> NotificationDeliveryResult:
    started = time.perf_counter()
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "QuantOdysseySupervisor/1.0",
    }
    secret = os.getenv("N8N_WEBHOOK_SECRET")
    if secret and "/webhook/" in url:
        headers["X-QuantOdyssey-Webhook-Secret"] = secret
    request = Request(url, data=body, method="POST", headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            latency_ms = int((time.perf_counter() - started) * 1000)
            if 200 <= int(response.status) < 300:
                return NotificationDeliveryResult(channel, "ok", f"{url} returned HTTP {response.status}.", latency_ms)
            return NotificationDeliveryResult(
                channel,
                "fail",
                f"{url} returned unexpected HTTP {response.status}.",
                latency_ms,
            )
    except HTTPError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return NotificationDeliveryResult(channel, "fail", f"{url} returned HTTP {exc.code}.", latency_ms)
    except (TimeoutError, URLError) as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return NotificationDeliveryResult(channel, "fail", f"{url} failed: {exc.__class__.__name__}.", latency_ms)


def delivery_results_to_dict(results: list[NotificationDeliveryResult]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]
