#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.vps.yml}"
PAIR="${FREQTRADE_PAIR:-BTC/USDT}"
TIMEFRAME="${FREQTRADE_TIMEFRAME:-5m}"
DAYS="${FREQTRADE_DAYS:-30}"
DATA_FILE="${FREQTRADE_DATA_FILE:-/app/freqtrade_user_data/data/binance/BTC_USDT-5m.feather}"

docker compose -f "$COMPOSE_FILE" exec -T app \
  python scripts/download_freqtrade_data.py \
  --pairs "$PAIR" \
  --timeframes "$TIMEFRAME" \
  --days "$DAYS" \
  --config configs/freqtrade_config.json \
  --freqtrade-bin freqtrade

docker compose -f "$COMPOSE_FILE" exec -T app \
  python scripts/import_freqtrade_market_data.py \
  --data-file "$DATA_FILE" \
  --symbol "$PAIR" \
  --interval "$TIMEFRAME" \
  --min-rank "${MARKET_SIGNAL_MIN_RANK:-70}"
