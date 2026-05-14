#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-45.32.44.245}"
USER="${2:-codexboy}"
REMOTE_DIR="${3:-/home/codexboy/QuantOdyssey}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required on the local machine" >&2
  exit 1
fi

rsync -az --delete \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude ".venv311" \
  --exclude ".tools" \
  --exclude ".env" \
  --exclude ".pytest_cache" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude "*.sqlite3" \
  --exclude "caddy/auth.caddy" \
  --exclude "build" \
  --exclude "*.egg-info" \
  --exclude "schemas" \
  --exclude "logs" \
  --exclude "freqtrade_user_data/data" \
  --exclude "freqtrade_user_data/backtest_results" \
  --exclude "freqtrade_user_data/strategies/*.py" \
  ./ "$USER@$HOST:$REMOTE_DIR/"

ssh "$USER@$HOST" "cd '$REMOTE_DIR' && test -f .env || cp .env.vps.example .env"
ssh "$USER@$HOST" "cd '$REMOTE_DIR' && docker compose -f docker-compose.vps.yml up -d --build"
ssh "$USER@$HOST" "cd '$REMOTE_DIR' && docker compose -f docker-compose.vps.yml up -d --force-recreate caddy"
ssh "$USER@$HOST" "cd '$REMOTE_DIR' && docker compose -f docker-compose.vps.yml ps"
