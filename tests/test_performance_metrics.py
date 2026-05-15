from app.services.metrics import (
    compound_return,
    max_drawdown,
    max_drawdown_from_equity_returns,
    performance_metric_registry,
    profit_factor,
    return_stats,
    sharpe_ratio,
)


def test_performance_metrics_use_compounded_trade_level_principles() -> None:
    returns = [0.10, -0.05, 0.02]

    assert round(compound_return(returns), 6) == 0.0659
    assert round(profit_factor(returns), 6) == 2.4
    assert round(max_drawdown(returns), 6) == -0.05
    assert return_stats(returns)["average_return"] == sum(returns) / len(returns)


def test_profit_factor_unbounded_sentinel_and_tiny_volatility_sharpe_guard() -> None:
    assert profit_factor([0.01, 0.02]) == 99.0
    assert profit_factor([-0.01, -0.02]) == 0.0
    assert sharpe_ratio([0.01, 0.01, 0.01]) is None


def test_drawdown_from_mark_to_market_equity_curve() -> None:
    equity_returns = [0.0, 0.10, 0.045, 0.0659]

    assert round(max_drawdown_from_equity_returns(equity_returns), 6) == -0.05


def test_metric_registry_exposes_formulas_and_external_references() -> None:
    registry = performance_metric_registry()
    ids = {item.metric_id for item in registry}

    assert {"total_return", "profit_factor", "max_drawdown", "sharpe_ratio", "trade_count"} <= ids
    assert all(item.formula for item in registry)
    assert all(item.audit_checks for item in registry)
    assert any("freqtrade" in reference["url"] for item in registry for reference in item.external_references)
