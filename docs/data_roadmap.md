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
python scripts/check_backtest_environment.py
python scripts/download_freqtrade_data.py --trading-mode spot
python scripts/download_freqtrade_data.py --trading-mode futures
```

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
