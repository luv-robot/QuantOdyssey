from __future__ import annotations

import os
import shutil
import socket
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError


DEFAULT_TABLES = (
    "research_theses",
    "signals",
    "research_findings",
    "research_tasks",
    "research_harness_cycles",
    "event_definition_sensitivity_reports",
    "event_definition_universe_reports",
    "failed_breakout_sensitivity_reports",
    "failed_breakout_universe_reports",
    "strategy_registry",
    "backtests",
    "monte_carlo_backtests",
    "paper_trading_reports",
    "reviews",
)


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: str
    message: str
    latency_ms: int | None = None
    details: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class HealthReport:
    status: str
    generated_at: str
    checks: list[HealthCheck]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _check_database(database_url: str | None) -> HealthCheck:
    if not database_url:
        return HealthCheck("database", "warn", "DATABASE_URL is not configured.")

    started = time.perf_counter()
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("select 1"))
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            counts = {}
            for table in DEFAULT_TABLES:
                if table in tables:
                    counts[table] = int(
                        connection.execute(text(f"select count(*) from {table}")).scalar() or 0
                    )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return HealthCheck(
            "database",
            "ok",
            "Database connection is healthy.",
            latency_ms=latency_ms,
            details={"table_counts": counts},
        )
    except SQLAlchemyError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return HealthCheck(
            "database",
            "fail",
            f"Database check failed: {exc.__class__.__name__}",
            latency_ms=latency_ms,
        )


def _http_check(name: str, url: str | None, expected_statuses: set[int]) -> HealthCheck:
    if not url:
        return HealthCheck(name, "warn", f"{name.upper()} URL is not configured.")

    started = time.perf_counter()
    request = Request(url, method="GET", headers={"User-Agent": "QuantOdysseyHealth/1.0"})
    try:
        with urlopen(request, timeout=5) as response:
            status = int(response.status)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if status in expected_statuses:
                return HealthCheck(name, "ok", f"{url} returned HTTP {status}.", latency_ms)
            return HealthCheck(name, "fail", f"{url} returned unexpected HTTP {status}.", latency_ms)
    except HTTPError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        if exc.code in expected_statuses:
            return HealthCheck(name, "ok", f"{url} returned HTTP {exc.code}.", latency_ms)
        return HealthCheck(name, "fail", f"{url} returned HTTP {exc.code}.", latency_ms)
    except (URLError, TimeoutError, socket.timeout) as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return HealthCheck(name, "fail", f"{url} check failed: {exc.__class__.__name__}", latency_ms)


def _disk_check(path: str, warn_percent: int) -> HealthCheck:
    if not os.path.exists(path):
        path = os.getcwd()
    usage = shutil.disk_usage(path)
    used_percent = round((usage.used / usage.total) * 100, 1)
    status = "warn" if used_percent >= warn_percent else "ok"
    return HealthCheck(
        "disk",
        status,
        f"{path} disk usage is {used_percent}%.",
        details={
            "path": path,
            "used_percent": used_percent,
            "free_gb": round(usage.free / 1024 / 1024 / 1024, 2),
        },
    )


def _secret_check() -> HealthCheck:
    secret = os.getenv("N8N_WEBHOOK_SECRET", "")
    if len(secret) >= 24:
        return HealthCheck("webhook_secret", "ok", "N8N_WEBHOOK_SECRET is configured.")
    if secret:
        return HealthCheck("webhook_secret", "warn", "N8N_WEBHOOK_SECRET is short.")
    return HealthCheck("webhook_secret", "fail", "N8N_WEBHOOK_SECRET is not configured.")


def run_health_checks() -> HealthReport:
    checks = [
        _check_database(os.getenv("DATABASE_URL")),
        _http_check("qdrant", os.getenv("QDRANT_URL"), {200}),
        _http_check("prefect", _normalize_api_url(os.getenv("PREFECT_API_URL")), {200, 307, 308}),
        _http_check("n8n", os.getenv("N8N_URL"), {200, 401}),
        _disk_check(os.getenv("HEALTH_DISK_PATH", "/app"), int(os.getenv("DISK_WARN_PERCENT", "85"))),
        _secret_check(),
    ]
    status = "ok"
    if any(check.status == "fail" for check in checks):
        status = "fail"
    elif any(check.status == "warn" for check in checks):
        status = "warn"
    return HealthReport(status=status, generated_at=_now_iso(), checks=checks)


def _normalize_api_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/") + "/health"
