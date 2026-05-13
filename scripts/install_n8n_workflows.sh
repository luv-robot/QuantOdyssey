#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.vps.yml}"

docker compose -f "$COMPOSE_FILE" exec -T n8n \
  n8n import:workflow --input=/files/n8n/workflows/research_thesis_webhook.json

docker compose -f "$COMPOSE_FILE" exec -T n8n \
  n8n list:workflow
