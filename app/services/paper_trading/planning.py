from __future__ import annotations

from app.models import BacktestReport, MarketSignal, PaperTradingPlan, PaperTradingPlanStatus, StrategyManifest


def build_paper_trading_plan(
    signal: MarketSignal,
    strategy: StrategyManifest,
    backtest: BacktestReport,
    has_recent_candles: bool = False,
) -> PaperTradingPlan:
    return PaperTradingPlan(
        plan_id=f"paper_plan_{strategy.strategy_id}",
        strategy_id=strategy.strategy_id,
        signal_id=signal.signal_id,
        backtest_id=backtest.backtest_id,
        status=PaperTradingPlanStatus.READY_FOR_PAPER if has_recent_candles else PaperTradingPlanStatus.PENDING_DATA,
        required_symbol=signal.symbol,
        required_timeframe=signal.timeframe,
        notes=[
            "Selected candidate must pass paper trading before live-candidate promotion.",
            "Plan is waiting for recent candle stream." if not has_recent_candles else "Plan is ready for simulation.",
        ],
    )
