# Lean Strategy Catalog

QuantConnect Lean is useful to QuantOdyssey as a strategy sample and baseline-archetype source.
It should not be treated as a ready-made alpha library.

## Import Boundary

The importer records metadata only:

- source path
- language
- algorithm class name
- asset classes
- indicators
- resolution hints
- data requirements
- strategy-family guess
- migration difficulty
- suggested role

It does not copy strategy source code into QuantOdyssey, does not execute Lean strategies, and does
not mark any imported item as validated.

## Suggested Roles

- `sample_strategy`: useful example for humans or agents.
- `baseline_candidate`: simple OHLCV/indicator pattern that may become a generic baseline after review.
- `strategy_family_template`: reusable strategy-family archetype.
- `agent_eval_case`: complex strategy useful for testing whether AI can detect data/runtime mismatch.
- `crypto_porting_candidate`: likely closer to the current crypto/Freqtrade runtime.

## Import Command

```bash
python scripts/import_lean_strategy_catalog.py --save-to-db
```

Use a local Lean checkout if already available:

```bash
python scripts/import_lean_strategy_catalog.py --lean-path /path/to/Lean --save-to-db
```

Limit the scan during smoke tests:

```bash
python scripts/import_lean_strategy_catalog.py --max-files 50 --output artifacts/lean_catalog_smoke.json
```

## Product Use

Imported records appear under the Dashboard `Strategy Catalog` tab.

The catalog should feed:

- baseline family expansion
- public starter examples
- agent eval cases
- strategy-family templates
- future Lean-native backtest adapter planning

Before a catalog item becomes a baseline, it still needs human review, data-contract validation,
matched backtests, and ReviewSession analysis.
