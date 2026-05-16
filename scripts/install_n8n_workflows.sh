#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.vps.yml}"

docker compose -f "$COMPOSE_FILE" exec -T n8n \
  n8n import:workflow --input=/files/n8n/workflows/research_thesis_webhook.json

docker compose -f "$COMPOSE_FILE" exec -T n8n \
  n8n import:workflow --input=/files/n8n/workflows/supervisor_system_alert_webhook.json

docker compose -f "$COMPOSE_FILE" exec -T n8n \
  n8n publish:workflow --id=quant-odyssey-research-thesis-intake

docker compose -f "$COMPOSE_FILE" exec -T n8n \
  n8n publish:workflow --id=quant-odyssey-supervisor-system-alert

docker compose -f "$COMPOSE_FILE" exec -T n8n \
  n8n list:workflow
