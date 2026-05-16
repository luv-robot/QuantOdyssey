from __future__ import annotations

import os

from app.models import BacktestCostModel


def default_backtest_cost_model_from_env(prefix: str = "QUANTODYSSEY") -> BacktestCostModel:
    """Load default research costs from env so user submissions can override them later."""
    return BacktestCostModel(
        fee_rate=_float_env(f"{prefix}_FEE_RATE", 0.0005),
        slippage_bps=_float_env(f"{prefix}_SLIPPAGE_BPS", 2.0),
        spread_bps=_float_env(f"{prefix}_SPREAD_BPS", 0.0),
        funding_rate_8h=_float_env(f"{prefix}_FUNDING_RATE_8H", 0.0),
        funding_source=os.getenv(f"{prefix}_FUNDING_SOURCE", "not_available"),
        notes=_split_notes(os.getenv(f"{prefix}_COST_NOTES", "")),
    )


def effective_freqtrade_fee_rate(cost_model: BacktestCostModel) -> float:
    """Freqtrade applies --fee on entry and exit, so add per-side slippage/spread here."""
    return cost_model.fee_rate + (cost_model.slippage_bps + cost_model.spread_bps) / 10_000


def round_trip_execution_cost(cost_model: BacktestCostModel, *, holding_hours: float = 0.0) -> float:
    execution_cost = 2 * effective_freqtrade_fee_rate(cost_model)
    funding_cost = abs(cost_model.funding_rate_8h) * max(holding_hours, 0.0) / 8
    return execution_cost + funding_cost


def cost_model_metadata(cost_model: BacktestCostModel) -> dict[str, object]:
    effective_fee = effective_freqtrade_fee_rate(cost_model)
    return {
        "fee_model": {
            "fee_rate": cost_model.fee_rate,
            "effective_freqtrade_fee_rate": effective_fee,
            "applied_twice_by_freqtrade": True,
        },
        "slippage_model": {
            "slippage_bps": cost_model.slippage_bps,
            "spread_bps": cost_model.spread_bps,
            "method": "added_to_freqtrade_fee_per_side",
        },
        "funding_model": {
            "funding_rate_8h": cost_model.funding_rate_8h,
            "funding_source": cost_model.funding_source,
        },
        "cost_model": cost_model.model_dump(mode="json"),
    }


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _split_notes(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]

