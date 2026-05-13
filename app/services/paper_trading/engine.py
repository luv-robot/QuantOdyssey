from __future__ import annotations

from dataclasses import dataclass

from app.models import (
    MarketSignal,
    OhlcvCandle,
    PaperEvaluationStatus,
    PaperFill,
    PaperOrder,
    PaperOrderSide,
    PaperOrderStatus,
    PaperPortfolio,
    PaperPosition,
    PaperPositionStatus,
    PaperTradingReport,
    StrategyManifest,
)


@dataclass(frozen=True)
class PaperTradingResult:
    portfolio: PaperPortfolio
    orders: list[PaperOrder]
    fills: list[PaperFill]
    positions: list[PaperPosition]
    report: PaperTradingReport


def run_paper_trading_simulation(
    signal: MarketSignal,
    strategy: StrategyManifest,
    candles: list[OhlcvCandle],
    starting_cash: float = 10_000,
    stake_fraction: float = 0.1,
    fee_rate: float = 0.001,
    slippage_rate: float = 0.0005,
) -> PaperTradingResult:
    if len(candles) < 2:
        portfolio = PaperPortfolio(
            portfolio_id=f"paper_{strategy.strategy_id}",
            starting_cash=starting_cash,
            cash=starting_cash,
            equity=starting_cash,
        )
        return PaperTradingResult(
            portfolio=portfolio,
            orders=[],
            fills=[],
            positions=[],
            report=PaperTradingReport(
                report_id=f"paper_report_{strategy.strategy_id}",
                strategy_id=strategy.strategy_id,
                portfolio_id=portfolio.portfolio_id,
                trades=0,
                win_rate=0,
                total_return=0,
                max_drawdown=0,
                profit_factor=0,
                status=PaperEvaluationStatus.RETIRED,
                notes=["Insufficient candles for paper trading simulation."],
            ),
        )

    entry = candles[0]
    exit_candle = candles[-1]
    stake = starting_cash * stake_fraction
    entry_price = entry.close * (1 + slippage_rate)
    exit_price = exit_candle.close * (1 - slippage_rate)
    quantity = stake / entry_price
    buy_fee = stake * fee_rate
    sell_value = quantity * exit_price
    sell_fee = sell_value * fee_rate
    realized_pnl = sell_value - stake - buy_fee - sell_fee
    ending_cash = starting_cash + realized_pnl
    total_return = realized_pnl / starting_cash

    buy_order = PaperOrder(
        order_id=f"paper_order_{strategy.strategy_id}_buy",
        strategy_id=strategy.strategy_id,
        symbol=signal.symbol,
        side=PaperOrderSide.BUY,
        quantity=quantity,
        requested_price=entry.close,
        status=PaperOrderStatus.FILLED,
    )
    sell_order = PaperOrder(
        order_id=f"paper_order_{strategy.strategy_id}_sell",
        strategy_id=strategy.strategy_id,
        symbol=signal.symbol,
        side=PaperOrderSide.SELL,
        quantity=quantity,
        requested_price=exit_candle.close,
        status=PaperOrderStatus.FILLED,
    )
    fills = [
        PaperFill(
            fill_id=f"paper_fill_{strategy.strategy_id}_buy",
            order_id=buy_order.order_id,
            strategy_id=strategy.strategy_id,
            symbol=signal.symbol,
            side=PaperOrderSide.BUY,
            quantity=quantity,
            price=entry_price,
            fee=buy_fee,
            slippage=entry_price - entry.close,
        ),
        PaperFill(
            fill_id=f"paper_fill_{strategy.strategy_id}_sell",
            order_id=sell_order.order_id,
            strategy_id=strategy.strategy_id,
            symbol=signal.symbol,
            side=PaperOrderSide.SELL,
            quantity=quantity,
            price=exit_price,
            fee=sell_fee,
            slippage=exit_candle.close - exit_price,
        ),
    ]
    position = PaperPosition(
        position_id=f"paper_position_{strategy.strategy_id}",
        strategy_id=strategy.strategy_id,
        symbol=signal.symbol,
        quantity=quantity,
        entry_price=entry_price,
        exit_price=exit_price,
        realized_pnl=realized_pnl,
        status=PaperPositionStatus.CLOSED,
        opened_at=entry.open_time,
        closed_at=exit_candle.close_time,
    )
    portfolio = PaperPortfolio(
        portfolio_id=f"paper_{strategy.strategy_id}",
        starting_cash=starting_cash,
        cash=ending_cash,
        equity=ending_cash,
    )
    status = (
        PaperEvaluationStatus.LIVE_CANDIDATE
        if total_return > 0 and realized_pnl > 0
        else PaperEvaluationStatus.RETIRED
    )
    report = PaperTradingReport(
        report_id=f"paper_report_{strategy.strategy_id}",
        strategy_id=strategy.strategy_id,
        portfolio_id=portfolio.portfolio_id,
        trades=1,
        win_rate=1 if realized_pnl > 0 else 0,
        total_return=round(total_return, 6),
        max_drawdown=min(0, round(total_return, 6)),
        profit_factor=round(1 + max(total_return, 0) * 10, 6) if realized_pnl > 0 else 0,
        status=status,
        notes=["Paper simulation uses deterministic one-entry one-exit execution."],
    )
    return PaperTradingResult(
        portfolio=portfolio,
        orders=[buy_order, sell_order],
        fills=fills,
        positions=[position],
        report=report,
    )
