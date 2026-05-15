# WorldQuant-Style Factor Catalog

WorldQuant 101 is useful to QuantOdyssey as a factor grammar and baseline source, not as a ready-made
alpha library.

## Boundary

The catalog stores metadata-only formula templates:

- factor family
- pseudo formula expression
- required fields
- required operators
- evaluation scope
- data sufficiency level
- implementation status
- overfitting warnings

It does not copy third-party GitHub implementations, does not import external source code, and does not
mark any factor as validated alpha.

## Product Use

The catalog helps the system answer:

- Is a submitted thesis just a common momentum, reversal, volatility, or price-volume factor?
- Which baselines should be run before treating a thesis as interesting?
- Does this idea require cross-sectional universe data?
- Is OHLCV enough, or does the thesis require funding, OI, or orderflow?

## Seed Command

```bash
python scripts/seed_factor_formula_catalog.py --save-to-db
```

Export without database writes:

```bash
python scripts/seed_factor_formula_catalog.py --output artifacts/worldquant_style_factors.json
```

## Current Policy

Early QuantOdyssey should use these formulas as:

- baseline candidates
- commonness-risk references
- strategy-family templates
- agent eval cases

Before a factor becomes a runnable baseline, it still needs a data contract, a deterministic
implementation, matched benchmark tests, and ReviewSession analysis.
