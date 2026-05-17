# Backtest Cost Policy

QuantOdyssey strategy tests must report net results after default research costs.

## Defaults

- Trading fee: `0.0005` per side.
- Slippage: `2.0` bps per side.
- Spread proxy: `0.0` bps per side.
- Funding rate: `0.0` per 8h unless a real funding source is available.

For Freqtrade backtests, the effective `--fee` is:

```text
effective_freqtrade_fee_rate = fee_rate + (slippage_bps + spread_bps) / 10000
```

Freqtrade applies `--fee` on entry and exit, so this models round-trip fee plus
round-trip slippage/spread.

For lightweight harness event simulations, the per-trade cost is:

```text
round_trip_cost =
  2 * (fee_rate + (slippage_bps + spread_bps) / 10000)
  + abs(funding_rate_8h) * holding_hours / 8
```

The same helper is used by strategy-family baseline simulations and thesis-level
baseline comparisons, so gross baseline signals must beat the configured
round-trip cost before they are treated as net evidence.

## Overrides

Operators can override defaults with environment variables:

```text
QUANTODYSSEY_FEE_RATE
QUANTODYSSEY_SLIPPAGE_BPS
QUANTODYSSEY_SPREAD_BPS
QUANTODYSSEY_FUNDING_RATE_8H
QUANTODYSSEY_FUNDING_SOURCE
```

Baseline scans also accept CLI overrides:

```bash
python scripts/run_baseline_regime_scan.py \
  --fee-rate 0.0005 \
  --slippage-bps 2 \
  --spread-bps 0 \
  --funding-rate-8h 0
```

Harness event validation accepts:

```bash
python scripts/run_harness_tasks.py \
  --walk-forward-fee-rate 0.001 \
  --walk-forward-slippage-bps 2 \
  --walk-forward-funding-rate-8h 0
```

## Reporting Rules

- `total_return`, `profit_factor`, and `max_drawdown` are net metrics.
- Baseline rows also expose `gross_return`, `net_return`, `cost_drag`,
  `fee_drag`, `slippage_drag`, and `funding_drag`.
- Thesis-level baseline comparisons report `return_basis=net_after_costs` and
  persist the cost model used by the review.
- ReviewSession scorecards must cite the net baseline return basis and the cost
  assumptions used for the comparison.
- Mixed-timeframe baseline boards are aligned to a common overlapping window by
  default.
- Timeframe-separated baseline boards are emitted for supervision and calibration.
