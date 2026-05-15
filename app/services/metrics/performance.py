from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from statistics import mean, pstdev


UNBOUNDED_PROFIT_FACTOR = 99.0


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    display_name: str
    category: str
    description: str
    formula: str
    unit: str
    implementation_notes: list[str]
    audit_checks: list[str]
    external_references: list[dict[str, str]]

    def to_record(self) -> dict:
        return asdict(self)


def gross_profit(returns: list[float]) -> float:
    return sum(item for item in returns if item > 0)


def gross_loss(returns: list[float]) -> float:
    return abs(sum(item for item in returns if item < 0))


def profit_factor(returns: list[float], *, unbounded_value: float = UNBOUNDED_PROFIT_FACTOR) -> float:
    profit = gross_profit(returns)
    loss = gross_loss(returns)
    if loss > 0:
        return profit / loss
    return unbounded_value if profit > 0 else 0.0


def compound_return(returns: list[float]) -> float:
    equity = 1.0
    for item in returns:
        equity *= 1 + item
    return equity - 1


def max_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    for item in returns:
        equity *= 1 + item
        peak = max(peak, equity)
        if peak > 0:
            drawdown = min(drawdown, equity / peak - 1)
    return drawdown


def max_drawdown_from_equity_returns(equity_returns: list[float]) -> float:
    peak = 1.0
    drawdown = 0.0
    for item in equity_returns:
        equity = 1 + item
        peak = max(peak, equity)
        if peak > 0:
            drawdown = min(drawdown, equity / peak - 1)
    return drawdown


def sharpe_ratio(returns: list[float], *, annualization_factor: float | None = None) -> float | None:
    if len(returns) < 2:
        return None
    stdev = pstdev(returns)
    if stdev <= 1e-12:
        return None
    scale = sqrt(annualization_factor) if annualization_factor else sqrt(len(returns))
    return round(mean(returns) / stdev * scale, 6)


def return_stats(returns: list[float]) -> dict[str, float | None]:
    if not returns:
        return {
            "average_return": 0.0,
            "total_return": 0.0,
            "profit_factor": 0.0,
            "sharpe": None,
            "max_drawdown": 0.0,
        }
    return {
        "average_return": mean(returns),
        "total_return": compound_return(returns),
        "profit_factor": profit_factor(returns),
        "sharpe": sharpe_ratio(returns),
        "max_drawdown": max_drawdown(returns),
    }


def performance_metric_registry() -> list[MetricDefinition]:
    refs = _external_metric_references()
    return [
        MetricDefinition(
            metric_id="total_return",
            display_name="Total Return",
            category="performance",
            description="Compounded return of a sequence of completed trade or equity-period returns.",
            formula="total_return = product(1 + r_i) - 1",
            unit="decimal return",
            implementation_notes=[
                "Use compounded returns for sequential trades; do not sum returns except for quick diagnostics.",
                "When aggregating multiple market/timeframe cells, compute each cell's compounded return first, then aggregate cells explicitly.",
            ],
            audit_checks=[
                "For returns [0.10, -0.05, 0.02], total_return must equal 0.0659.",
                "A baseline row must state whether returns are trade-level, cell-level, or passive exposure-level.",
            ],
            external_references=refs["return"],
        ),
        MetricDefinition(
            metric_id="profit_factor",
            display_name="Profit Factor",
            category="performance",
            description="Gross winning trade returns divided by absolute gross losing trade returns.",
            formula="profit_factor = sum(max(r_i, 0)) / abs(sum(min(r_i, 0)))",
            unit="ratio",
            implementation_notes=[
                "Use completed trade returns, not market/timeframe cell returns.",
                "If there are gains and no losses, QuantOdyssey records 99.0 as an explicit unbounded sentinel.",
            ],
            audit_checks=[
                "For returns [0.10, -0.05, 0.02], profit_factor must equal 2.4.",
                "A tiny sample with zero losses must be flagged by sample-count controls instead of treated as high confidence.",
            ],
            external_references=refs["profit_factor"],
        ),
        MetricDefinition(
            metric_id="max_drawdown",
            display_name="Maximum Drawdown",
            category="risk",
            description="Worst peak-to-trough decline in the compounded equity curve.",
            formula="max_drawdown = min_t(equity_t / running_peak_t - 1)",
            unit="decimal return",
            implementation_notes=[
                "Compute from an equity curve, not from the worst individual trade or final total return.",
                "For buy-and-hold or DCA, build the mark-to-market equity curve over candles.",
            ],
            audit_checks=[
                "For returns [0.10, -0.05, 0.02], max_drawdown must equal -0.05.",
                "A positive buy-and-hold period can still have negative max_drawdown.",
            ],
            external_references=refs["drawdown"],
        ),
        MetricDefinition(
            metric_id="sharpe_ratio",
            display_name="Sharpe Ratio",
            category="risk_adjusted_return",
            description="Average excess return divided by return standard deviation, scaled by a declared sampling factor.",
            formula="sharpe = mean(r_i) / stddev(r_i) * sqrt(scale)",
            unit="ratio",
            implementation_notes=[
                "Current event/baseline helpers use per-trade returns with sqrt(number_of_trades) scaling.",
                "Freqtrade backtest Sharpe values are parsed from Freqtrade output and should not be mixed with per-trade proxy Sharpe without labeling.",
            ],
            audit_checks=[
                "If fewer than two returns exist or volatility is zero, Sharpe is None.",
                "Reports must label whether Sharpe is annualized time-series Sharpe or per-trade proxy Sharpe.",
            ],
            external_references=refs["sharpe"],
        ),
        MetricDefinition(
            metric_id="trade_count",
            display_name="Trade Count",
            category="sample_quality",
            description="Number of completed simulated trades included in a metric calculation.",
            formula="trade_count = count(completed trade returns)",
            unit="count",
            implementation_notes=[
                "Do not substitute symbol/timeframe cell count for active strategy trade count.",
                "Passive baselines should be treated as exposure samples and labeled accordingly.",
            ],
            audit_checks=[
                "Active baselines such as time_series_trend should usually have trade_count greater than tested_cell_count.",
                "A high profit factor with very small trade_count should be considered weak evidence.",
            ],
            external_references=refs["trade_count"],
        ),
    ]


def _external_metric_references() -> dict[str, list[dict[str, str]]]:
    freqtrade = {
        "name": "Freqtrade backtesting report",
        "url": "https://docs.freqtrade.io/en/stable/backtesting/",
        "note": "Operational reference for backtest report fields including profit factor, drawdown, and Sharpe-style metrics.",
    }
    quantconnect = {
        "name": "QuantConnect backtest statistics",
        "url": "https://www.quantconnect.com/docs/v2/our-platform/api-reference/backtest-management/read-backtest/backtest-statistics",
        "note": "Platform reference for common backtest statistics exposed by a mature quant platform.",
    }
    backtrader = {
        "name": "Backtrader analyzers reference",
        "url": "https://www.backtrader.com/docu/analyzers-reference/",
        "note": "Analyzer reference for independent checks of drawdown, Sharpe ratio, and trade analysis concepts.",
    }
    return {
        "return": [freqtrade, quantconnect],
        "profit_factor": [freqtrade, quantconnect, backtrader],
        "drawdown": [freqtrade, quantconnect, backtrader],
        "sharpe": [freqtrade, quantconnect, backtrader],
        "trade_count": [freqtrade, backtrader],
    }
