from __future__ import annotations

import os
import subprocess
from pathlib import Path

from prefect import flow, get_run_logger, task


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, check=check, text=True, capture_output=True)


@task(retries=1, retry_delay_seconds=60)
def run_harness_queue() -> None:
    logger = get_run_logger()
    symbols = _split_env("HARNESS_RUNNER_SYMBOLS", os.getenv("ORDERFLOW_SYMBOLS", "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT"))
    timeframes = _split_env("HARNESS_RUNNER_TIMEFRAMES", "5m,15m,1h")
    command = [
        "python",
        "scripts/run_harness_tasks.py",
        "--database-url",
        os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"),
        "--data-dir",
        os.getenv("HARNESS_RUNNER_DATA_DIR", "freqtrade_user_data/data/binance/futures"),
        "--scratchpad-dir",
        os.getenv("HARNESS_RUNNER_SCRATCHPAD_DIR", "/app/logs/harness_scratchpad"),
        "--max-tasks",
        os.getenv("HARNESS_RUNNER_MAX_TASKS", "4"),
        "--max-queue-scan",
        os.getenv("HARNESS_RUNNER_MAX_QUEUE_SCAN", "30"),
        "--max-candles",
        os.getenv("HARNESS_RUNNER_MAX_CANDLES", "5000"),
        "--max-trials",
        os.getenv("HARNESS_RUNNER_MAX_TRIALS", "40"),
        "--min-trade-count",
        os.getenv("HARNESS_RUNNER_MIN_TRADE_COUNT", "10"),
        "--monte-carlo-simulations",
        os.getenv("HARNESS_RUNNER_MONTE_CARLO_SIMULATIONS", "80"),
        "--monte-carlo-horizon-trades",
        os.getenv("HARNESS_RUNNER_MONTE_CARLO_HORIZON_TRADES", "20"),
        "--monte-carlo-expensive-threshold",
        os.getenv("HARNESS_RUNNER_MONTE_CARLO_EXPENSIVE_THRESHOLD", "250000"),
        "--walk-forward-folds",
        os.getenv("HARNESS_RUNNER_WALK_FORWARD_FOLDS", "3"),
        "--walk-forward-min-trades-per-window",
        os.getenv("HARNESS_RUNNER_WALK_FORWARD_MIN_TRADES_PER_WINDOW", "10"),
        "--walk-forward-min-pass-rate",
        os.getenv("HARNESS_RUNNER_WALK_FORWARD_MIN_PASS_RATE", "0.5"),
        "--walk-forward-horizon-hours",
        os.getenv("HARNESS_RUNNER_WALK_FORWARD_HORIZON_HOURS", "2"),
        "--walk-forward-fee-rate",
        os.getenv("HARNESS_RUNNER_WALK_FORWARD_FEE_RATE", "0.001"),
        "--walk-forward-slippage-bps",
        os.getenv("HARNESS_RUNNER_WALK_FORWARD_SLIPPAGE_BPS", "2.0"),
        "--walk-forward-funding-rate-8h",
        os.getenv("HARNESS_RUNNER_WALK_FORWARD_FUNDING_RATE_8H", "0.0"),
    ]
    if _truthy(os.getenv("HARNESS_RUNNER_SEED_MAINTENANCE_TASKS", "true")):
        command.append("--seed-maintenance-tasks")
    for symbol in symbols:
        command.extend(["--symbol", symbol])
    for timeframe in timeframes:
        command.extend(["--timeframe", timeframe])
    if _truthy(os.getenv("HARNESS_RUNNER_APPROVE_EXPENSIVE_MONTE_CARLO", "")):
        command.append("--approve-expensive-monte-carlo")

    result = _run(command, check=False)
    if result.returncode != 0:
        logger.warning("Harness runner failed:\n%s\n%s", result.stdout, result.stderr)
        raise RuntimeError("Harness runner failed.")
    logger.info("Harness runner completed:\n%s", result.stdout)


@flow(name="research-harness-runner-flow")
def research_harness_runner_flow() -> None:
    run_harness_queue()


def _split_env(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    research_harness_runner_flow.serve(
        name="research-harness-runner",
        cron=os.getenv("HARNESS_RUNNER_CRON", "45 */2 * * *"),
        tags=["research-harness", "automation", "validation"],
    )
