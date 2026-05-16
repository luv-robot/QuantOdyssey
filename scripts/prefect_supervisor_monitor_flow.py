from __future__ import annotations

import os
import subprocess
from pathlib import Path

from prefect import flow, get_run_logger, task


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, check=check, text=True, capture_output=True)


@task(retries=1, retry_delay_seconds=60)
def run_supervisor_system_monitor() -> None:
    logger = get_run_logger()
    command = [
        "python",
        "scripts/run_supervisor_system_monitor.py",
        "--database-url",
        os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"),
        "--state-path",
        os.getenv("SUPERVISOR_ALERT_STATE_PATH", "/app/logs/supervisor_alert_state.json"),
    ]
    if _truthy(os.getenv("SUPERVISOR_ALERT_ON_WARN", "")):
        command.append("--alert-on-warn")
    result = _run(command, check=False)
    if result.returncode != 0:
        logger.warning("Supervisor system monitor failed:\n%s\n%s", result.stdout, result.stderr)
        raise RuntimeError("Supervisor system monitor failed.")
    logger.info("Supervisor system monitor completed:\n%s", result.stdout)


@flow(name="supervisor-system-monitor-flow")
def supervisor_system_monitor_flow() -> None:
    run_supervisor_system_monitor()


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    supervisor_system_monitor_flow.serve(
        name="supervisor-system-monitor",
        cron=os.getenv("SUPERVISOR_MONITOR_CRON", "*/15 * * * *"),
        tags=["supervisor", "operations", "alerts"],
    )
