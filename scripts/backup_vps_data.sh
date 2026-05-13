#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.vps.yml}"
BACKUP_ROOT="${BACKUP_ROOT:-/home/codexboy/quantodyssey_backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"

cd "${ROOT_DIR}"
mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_ROOT}" "${BACKUP_DIR}"

echo "Creating QuantOdyssey backup in ${BACKUP_DIR}"

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  pg_dump -U quant -d quant_odyssey --format=custom --file=/tmp/quant_odyssey.dump
docker compose -f "${COMPOSE_FILE}" cp postgres:/tmp/quant_odyssey.dump \
  "${BACKUP_DIR}/postgres_quant_odyssey.dump"
docker compose -f "${COMPOSE_FILE}" exec -T postgres rm -f /tmp/quant_odyssey.dump

backup_volume() {
  local volume_name="$1"
  local output_name="$2"
  docker run --rm \
    -v "${volume_name}:/data:ro" \
    -v "${BACKUP_DIR}:/backup" \
    alpine:3.20 \
    tar czf "/backup/${output_name}.tar.gz" -C /data .
}

backup_volume quantodyssey_n8n_data n8n_data
backup_volume quantodyssey_prefect_data prefect_data
backup_volume quantodyssey_caddy_data caddy_data
backup_volume quantodyssey_freqtrade_data freqtrade_data
backup_volume quantodyssey_app_logs app_logs

tar czf "${BACKUP_DIR}/runtime_config.tar.gz" \
  --exclude='.env' \
  --exclude='caddy/auth.caddy' \
  Caddyfile docker-compose.vps.yml configs n8n docs/operations

sha256sum "${BACKUP_DIR}"/* > "${BACKUP_DIR}/SHA256SUMS"

find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -print -exec rm -rf {} \;

echo "Backup complete: ${BACKUP_DIR}"
