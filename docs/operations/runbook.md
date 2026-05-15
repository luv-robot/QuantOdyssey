# Operations Runbook

## Health Checks

Run locally on the VPS:

```bash
cd /home/codexboy/QuantOdyssey
docker compose -f docker-compose.vps.yml exec -T app python scripts/check_system_health.py
```

The same checks are visible in the Dashboard under `System Status`.

## Orderflow Collector

The VPS runs a continuous Binance aggTrades collector as `orderflow-collector`.
By default it collects BTC/USDT, ETH/USDT, and SOL/USDT futures every 60 seconds,
stores raw aggregate trades, and builds 1m orderflow bars.

Check status:

```bash
cd /home/codexboy/QuantOdyssey
docker compose -f docker-compose.vps.yml ps orderflow-collector
docker compose -f docker-compose.vps.yml logs --tail=20 orderflow-collector
docker compose -f docker-compose.vps.yml exec -T app python scripts/check_orderflow_health.py
```

Runtime knobs are read from `.env`:

```text
ORDERFLOW_SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT
ORDERFLOW_POLL_SECONDS=60
ORDERFLOW_MAX_PAGES_PER_SYMBOL=5
```

Backfill public Binance archive data:

```bash
cd /home/codexboy/QuantOdyssey
docker compose -f docker-compose.vps.yml exec -T app \
  python scripts/backfill_binance_agg_trades_archive.py \
  --symbols BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT \
  --start-date 2026-05-01 \
  --end-date 2026-05-01
```

Archive backfill saves structured orderflow bars by default. Use `--save-raw`
only for small windows because raw aggregate trades can grow quickly.

Backfill only dates that overlap Failed Breakout event windows:

```bash
cd /home/codexboy/QuantOdyssey
docker compose -f docker-compose.vps.yml exec -T app \
  python scripts/backfill_orderflow_for_failed_breakout_events.py \
  --max-days 3 \
  --execute
```

Omit `--execute` to print the event-date plan without downloading archive files.
Keep `--max-days` small until the planned symbols and dates look reasonable.

Orderflow validation is scheduled by `orderflow-validation-scheduler`.
It runs health checks and Failed Breakout orderflow acceptance validation every 6 hours by default.

## Research Harness Runner

The VPS runs low-risk proposed research tasks through `harness-runner-scheduler`.
By default it scans the queue every 2 hours and only executes tasks that do not require human approval.
Current automatic task types include baseline, event-frequency, regime bucket, Monte Carlo, walk-forward,
and data-sufficiency review tasks.

Run a manual queue pass:

```bash
cd /home/codexboy/QuantOdyssey
docker compose -f docker-compose.vps.yml exec -T app \
  python scripts/run_harness_tasks.py \
  --max-tasks 4 \
  --max-queue-scan 30 \
  --symbol BTC/USDT:USDT \
  --symbol ETH/USDT:USDT \
  --symbol SOL/USDT:USDT \
  --timeframe 5m \
  --timeframe 15m \
  --timeframe 1h
```

Runtime knobs are read from `.env`:

```text
HARNESS_RUNNER_CRON=45 */2 * * *
HARNESS_RUNNER_MAX_TASKS=4
HARNESS_RUNNER_MAX_QUEUE_SCAN=30
HARNESS_RUNNER_TIMEFRAMES=5m,15m,1h
HARNESS_RUNNER_SCRATCHPAD_DIR=/app/logs/harness_scratchpad
```

The runner writes scratchpad JSONL files to `app_logs` so automatic research decisions can be audited.

## Backups

Run a manual backup on the VPS:

```bash
cd /home/codexboy/QuantOdyssey
./scripts/backup_vps_data.sh
```

Backups are written to:

```text
/home/codexboy/quantodyssey_backups
```

The script backs up Postgres, n8n, Prefect, Caddy certificates, Freqtrade data, app logs,
and non-secret runtime configuration. It keeps 14 days by default.

## Public Surface

Public ports should remain limited to:

```text
22/tcp
80/tcp
443/tcp
```

Streamlit, Prefect, n8n, Postgres, and Qdrant should listen on `127.0.0.1` only.
