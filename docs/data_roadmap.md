# Data Roadmap

QuantOdyssey should improve data capability in two stages.

## Stage 1: Free Data First

The platform should first make free or already-available data operationally useful before adding
paid vendors.

Priority:

1. Freqtrade spot OHLCV for major USDT pairs.
2. Freqtrade futures OHLCV for strategies that require shorting.
3. Binance public funding rate.
4. Binance public open interest.
5. Binance public orderbook snapshots where rate limits allow.
6. Internal data quality checks: missing files, wrong trading mode, stale data, insufficient
   timerange, and pair/timeframe coverage.

The system should never treat an environment failure as a strategy conclusion. If a short strategy
is evaluated with spot data, or if futures data is missing, the run should fail preflight and record
the exact missing capability.

Useful commands:

```bash
python scripts/audit_free_data_sources.py --skip-live
python scripts/audit_free_data_sources.py
python scripts/check_backtest_environment.py
python scripts/download_freqtrade_data.py --trading-mode spot
python scripts/download_freqtrade_data.py --trading-mode futures
python scripts/download_binance_open_interest.py --symbol BTC/USDT:USDT --period 5m --days 29
python scripts/import_freqtrade_market_data.py --data-file <ohlcv.feather> --funding-file <funding_rate.feather>
```

Current free data capability:

- Local Freqtrade spot and futures OHLCV coverage is preflighted before a real backtest starts.
- Freqtrade futures funding-rate feather files can be imported as historical funding evidence.
- Binance historical open-interest can be downloaded to a sidecar JSON file next to Freqtrade
  futures OHLCV and then consumed by Funding Crowding event generation. Binance only exposes a
  recent OI window, so the downloader caps requests at 29 days.
- Funding Crowding Fade has a first traceable event builder that derives funding percentile,
  failed-breakout state, VWAP distance, setup score, trigger score, and missing OI evidence from
  Freqtrade futures OHLCV + funding files. If an open-interest sidecar file is present, the event
  uses historical OI instead of the temporary volume proxy.
- Binance public endpoints cover spot/futures klines, funding rate, current open interest,
  historical open interest, and spot/futures orderbook snapshots.
- Binance public aggTrades collection is available for futures orderflow. The collector stores
  aggregate trades and derives 1m orderflow bars with taker buy/sell volume, taker buy ratio,
  net taker volume, and cumulative volume delta.
- Quality reports can flag missing candles, non-positive price/volume, invalid orderbooks, and
  stale funding/open-interest evidence.

### Tick / Orderflow Strategy Testing Readiness

Orderflow can start being used now as a validation layer for event-driven strategies, especially
Failed Breakout / liquidity-sweep style hypotheses. The currently supported path is:

```text
Binance aggTrades
→ AggregateTrade records
→ 1m OrderflowBar
→ event acceptance / conflict validation
→ ReviewSession evidence
```

This is enough to answer questions like:

- did aggressive buy flow continue after a failed upside breakout?
- did CVD confirm or conflict with the supposed trapped-side exit?
- did the strategy fail because the OHLCV trigger was wrong, or because orderflow contradicted it?

Full tick-level strategy backtesting should start after two conditions are met:

1. at least several days of continuous aggTrade/orderflow coverage exists for BTC/ETH/SOL; and
2. the event replay interface is in place, so a strategy can consume tick/orderflow events without
   pretending they are ordinary OHLCV candles.

Until then, tick/orderflow should not be used to declare strategy alpha. It should be used to
upgrade or reject the mechanism evidence behind OHLCV-discovered events.

## Stage 2: Paid Data By Evidence

Paid data should be introduced only after a thesis repeatedly reaches a clear data wall.

Budget requests should name:

- the strategy family blocked by missing data;
- the missing evidence, such as on-chain flow, labeled wallet activity, entity balances, exchange
  flow, liquidation detail, or derivatives positioning;
- the exact experiments that would become possible;
- the minimum subscription period needed to validate usefulness;
- the fallback if the paid data does not improve thesis discrimination.

Candidate paid vendors:

- Glassnode: on-chain and derivatives macro context.
- Nansen: labeled wallet/entity behavior and smart money/on-chain flow.

Until the system can explain why free data is insufficient for a specific thesis, paid data should
remain a planned integration point rather than an active dependency.
