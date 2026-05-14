from __future__ import annotations

import os
import subprocess
from pathlib import Path

from prefect import flow, get_run_logger, task


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, check=check, text=True, capture_output=True)


@task(retries=1, retry_delay_seconds=60)
def check_orderflow_health() -> None:
    logger = get_run_logger()
    result = _run(["python", "scripts/check_orderflow_health.py"], check=False)
    if result.returncode != 0:
        logger.warning("Orderflow health check failed:\n%s", result.stdout or result.stderr)
        raise RuntimeError("Orderflow health check failed.")
    logger.info("Orderflow health check passed:\n%s", result.stdout)


@task(retries=1, retry_delay_seconds=60)
def run_orderflow_acceptance_validation() -> None:
    logger = get_run_logger()
    symbols = _split_env("ORDERFLOW_VALIDATION_SYMBOLS", os.getenv("ORDERFLOW_SYMBOLS", "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT"))
    timeframes = _split_env("ORDERFLOW_VALIDATION_TIMEFRAMES", "1h")
    command = [
        "python",
        "scripts/run_orderflow_acceptance_validation.py",
        "--strategy-family",
        os.getenv("ORDERFLOW_VALIDATION_STRATEGY_FAMILY", "failed_breakout_punishment"),
        "--data-dir",
        os.getenv("ORDERFLOW_VALIDATION_DATA_DIR", "freqtrade_user_data/data/binance/futures"),
        "--max-candles",
        os.getenv("ORDERFLOW_VALIDATION_MAX_CANDLES", "20000"),
        "--min-events-with-orderflow",
        os.getenv("ORDERFLOW_VALIDATION_MIN_EVENTS_WITH_ORDERFLOW", "30"),
        "--min-confirmation-rate",
        os.getenv("ORDERFLOW_VALIDATION_MIN_CONFIRMATION_RATE", "0.5"),
        "--max-conflict-rate",
        os.getenv("ORDERFLOW_VALIDATION_MAX_CONFLICT_RATE", "0.35"),
        "--save",
    ]
    for symbol in symbols:
        command.extend(["--symbol", symbol])
    for timeframe in timeframes:
        command.extend(["--timeframe", timeframe])
    result = _run(command, check=False)
    if result.returncode != 0:
        logger.warning("Orderflow validation failed:\n%s\n%s", result.stdout, result.stderr)
        raise RuntimeError("Orderflow validation failed.")
    logger.info("Orderflow validation completed:\n%s", result.stdout)


@flow(name="orderflow-validation-flow")
def orderflow_validation_flow() -> None:
    check_orderflow_health()
    run_orderflow_acceptance_validation()


def _split_env(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


if __name__ == "__main__":
    orderflow_validation_flow.serve(
        name="orderflow-validation",
        cron=os.getenv("ORDERFLOW_VALIDATION_CRON", "15 */6 * * *"),
        tags=["market-data", "orderflow", "validation"],
    )
