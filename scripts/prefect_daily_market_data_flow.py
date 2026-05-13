from __future__ import annotations

import os
import subprocess
from pathlib import Path

from prefect import flow, get_run_logger, task


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


@task(retries=2, retry_delay_seconds=60)
def download_freqtrade_data() -> None:
    logger = get_run_logger()
    pair = os.getenv("FREQTRADE_PAIR", "BTC/USDT")
    timeframe = os.getenv("FREQTRADE_TIMEFRAME", "5m")
    days = os.getenv("FREQTRADE_DAYS", "30")
    logger.info("Downloading Freqtrade data for %s %s (%s days).", pair, timeframe, days)
    _run(
        [
            "python",
            "scripts/download_freqtrade_data.py",
            "--pairs",
            pair,
            "--timeframes",
            timeframe,
            "--days",
            days,
            "--config",
            "configs/freqtrade_config.json",
            "--freqtrade-bin",
            "freqtrade",
        ]
    )


@task(retries=2, retry_delay_seconds=60)
def import_market_data() -> None:
    logger = get_run_logger()
    pair = os.getenv("FREQTRADE_PAIR", "BTC/USDT")
    timeframe = os.getenv("FREQTRADE_TIMEFRAME", "5m")
    data_file = os.getenv(
        "FREQTRADE_DATA_FILE",
        "/app/freqtrade_user_data/data/binance/BTC_USDT-5m.feather",
    )
    min_rank = os.getenv("MARKET_SIGNAL_MIN_RANK", "1")
    logger.info("Importing %s and generating signals with min rank %s.", data_file, min_rank)
    _run(
        [
            "python",
            "scripts/import_freqtrade_market_data.py",
            "--data-file",
            data_file,
            "--symbol",
            pair,
            "--interval",
            timeframe,
            "--min-rank",
            min_rank,
        ]
    )


@flow(name="daily-market-data-flow")
def daily_market_data_flow() -> None:
    download_freqtrade_data()
    import_market_data()


if __name__ == "__main__":
    daily_market_data_flow.serve(
        name="daily-market-data",
        cron=os.getenv("DAILY_MARKET_DATA_CRON", "30 0 * * *"),
        tags=["market-data", "freqtrade", "phase-1"],
    )
