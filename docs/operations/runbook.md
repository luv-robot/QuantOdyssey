# Operations Runbook

## Health Checks

Run locally on the VPS:

```bash
cd /home/codexboy/QuantOdyssey
docker compose -f docker-compose.vps.yml exec -T app python scripts/check_system_health.py
```

The same checks are visible in the Dashboard under `System Status`.

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
