from __future__ import annotations

from datetime import datetime
from statistics import mean, pstdev
from typing import Any

from app.models import (
    BacktestReport,
    EnhancedReviewMetrics,
    FailureDiagnosis,
    MarketRegime,
    MarketSignal,
    MonteCarloBacktestReport,
    OhlcvCandle,
    RegimeReview,
    TradeRecord,
    TradeSummary,
)


def parse_freqtrade_trades(
    strategy_id: str,
    symbol: str,
    payload: list[dict[str, Any]],
) -> list[TradeRecord]:
    trades = []
    for index, row in enumerate(payload):
        profit_abs = float(row.get("profit_abs", row.get("profit", 0)))
        profit_pct = float(row.get("profit_pct", row.get("profit_ratio", 0)))
        trades.append(
            TradeRecord(
                trade_id=str(row.get("trade_id", f"{strategy_id}_trade_{index}")),
                strategy_id=strategy_id,
                symbol=symbol,
                opened_at=_parse_dt(row.get("open_date") or row.get("opened_at")),
                closed_at=_parse_dt(row.get("close_date") or row.get("closed_at")),
                entry_price=float(row.get("open_rate") or row.get("entry_price")),
                exit_price=float(row.get("close_rate") or row.get("exit_price")),
                quantity=float(row.get("amount") or row.get("quantity") or 1),
                profit_abs=profit_abs,
                profit_pct=profit_pct,
                fees=float(row.get("fee", row.get("fees", 0))),
            )
        )
    return trades


def summarize_trades(strategy_id: str, trades: list[TradeRecord]) -> TradeSummary:
    wins = [trade for trade in trades if trade.profit_pct > 0]
    losses = [trade for trade in trades if trade.profit_pct <= 0]
    total_profit_abs = sum(trade.profit_abs for trade in trades)
    total_profit_pct = sum(trade.profit_pct for trade in trades)
    return TradeSummary(
        strategy_id=strategy_id,
        trades=len(trades),
        wins=len(wins),
        losses=len(losses),
        win_rate=0 if not trades else len(wins) / len(trades),
        total_profit_abs=round(total_profit_abs, 6),
        total_profit_pct=round(total_profit_pct, 6),
        average_profit_pct=0 if not trades else round(total_profit_pct / len(trades), 6),
        largest_loss_pct=0 if not trades else min(trade.profit_pct for trade in trades),
        largest_win_pct=0 if not trades else max(trade.profit_pct for trade in trades),
    )


def classify_market_regime(candles: list[OhlcvCandle], funding_rate: float = 0) -> MarketRegime:
    if abs(funding_rate) >= 0.001:
        return MarketRegime.FUNDING_EXTREME
    if len(candles) < 5:
        return MarketRegime.RANGING

    closes = [candle.close for candle in candles]
    volumes = [candle.volume for candle in candles]
    returns = [(closes[index] - closes[index - 1]) / closes[index - 1] for index in range(1, len(closes))]
    volatility = pstdev(returns) if len(returns) > 1 else 0
    total_move = (closes[-1] - closes[0]) / closes[0]
    avg_volume = mean(volumes)

    if avg_volume < 1:
        return MarketRegime.LOW_LIQUIDITY
    if volatility >= 0.03:
        return MarketRegime.HIGH_VOLATILITY
    if total_move <= -0.05:
        return MarketRegime.MARKET_SYNC_DOWN
    if abs(total_move) >= 0.03:
        return MarketRegime.TRENDING
    return MarketRegime.RANGING


def review_by_regime(
    strategy_id: str,
    trades: list[TradeRecord],
    regime: MarketRegime,
) -> RegimeReview:
    summary = summarize_trades(strategy_id, trades)
    notes = []
    if summary.trades == 0:
        notes.append("No trades were available for this regime.")
    elif summary.total_profit_pct < 0:
        notes.append(f"Strategy lost money in {regime.value} regime.")
    else:
        notes.append(f"Strategy was profitable in {regime.value} regime.")

    return RegimeReview(
        strategy_id=strategy_id,
        regime=regime,
        trades=summary.trades,
        total_profit_pct=summary.total_profit_pct,
        win_rate=summary.win_rate,
        notes=notes,
    )


def build_enhanced_review_metrics(
    signal: MarketSignal,
    strategy_id: str,
    trades: list[TradeRecord],
    candles: list[OhlcvCandle],
    funding_rate: float = 0,
    backtest: BacktestReport | None = None,
    monte_carlo: MonteCarloBacktestReport | None = None,
    template_name: str | None = None,
) -> EnhancedReviewMetrics:
    summary = summarize_trades(strategy_id, trades)
    regime = classify_market_regime(candles, funding_rate=funding_rate)
    regime_review = review_by_regime(strategy_id, trades, regime)
    expected_return = (signal.rank_score - 50) / 100
    rank_return_alignment = summary.total_profit_pct - expected_return
    failure_patterns = []
    reusable_lessons = []

    if summary.trades == 0:
        failure_patterns.append("no_trades")
        reusable_lessons.append("Reject strategies that cannot produce paper or backtest trades.")
    if summary.total_profit_pct < 0:
        failure_patterns.append(f"loss_in_{regime.value}")
        reusable_lessons.append(f"Add filters before trading in {regime.value} market regime.")
    if rank_return_alignment < -0.1:
        failure_patterns.append("rank_return_mismatch")
        reusable_lessons.append("Recalibrate signal rank scoring against realized returns.")
    diagnoses = diagnose_strategy_failure(
        signal=signal,
        summary=summary,
        regime=regime,
        backtest=backtest,
        monte_carlo=monte_carlo,
        template_name=template_name,
    )
    reusable_lessons.extend(diagnosis.recommendation for diagnosis in diagnoses)
    evaluation_components = calculate_evaluation_components(
        summary=summary,
        backtest=backtest,
        monte_carlo=monte_carlo,
    )

    return EnhancedReviewMetrics(
        strategy_id=strategy_id,
        signal_id=signal.signal_id,
        signal_rank_score=signal.rank_score,
        realized_return=summary.total_profit_pct,
        rank_return_alignment=round(rank_return_alignment, 6),
        trade_summary=summary,
        regime_reviews=[regime_review],
        failure_patterns=failure_patterns,
        reusable_lessons=list(dict.fromkeys(reusable_lessons))
        or ["Keep regime-tagged performance in future strategy context."],
        failure_diagnoses=diagnoses,
        evaluation_score=calculate_evaluation_score(evaluation_components),
        evaluation_components=evaluation_components,
    )


def calculate_evaluation_components(
    summary: TradeSummary,
    backtest: BacktestReport | None = None,
    monte_carlo: MonteCarloBacktestReport | None = None,
) -> dict[str, float]:
    profit_factor = 0 if backtest is None else backtest.profit_factor
    sharpe = 0 if backtest is None or backtest.sharpe is None else backtest.sharpe
    drawdown_abs = 0 if backtest is None else abs(backtest.max_drawdown)
    calmar = 0 if backtest is None or drawdown_abs == 0 else backtest.total_return / drawdown_abs
    probability_of_loss = 1 if monte_carlo is None else monte_carlo.probability_of_loss
    return {
        "profit_factor_score": _score(profit_factor / 1.8),
        "sharpe_score": _score((sharpe + 1) / 3),
        "calmar_score": _score((calmar + 1) / 3),
        "win_rate_score": _score(summary.win_rate / 0.55),
        "drawdown_score": _score((0.2 - drawdown_abs) / 0.2),
        "monte_carlo_score": _score(1 - probability_of_loss),
    }


def calculate_evaluation_score(components: dict[str, float]) -> float:
    weights = {
        "profit_factor_score": 0.25,
        "sharpe_score": 0.2,
        "calmar_score": 0.15,
        "win_rate_score": 0.1,
        "drawdown_score": 0.1,
        "monte_carlo_score": 0.2,
    }
    return round(sum(components.get(key, 0) * weight for key, weight in weights.items()), 2)


def diagnose_strategy_failure(
    signal: MarketSignal,
    summary: TradeSummary,
    regime: MarketRegime,
    backtest: BacktestReport | None = None,
    monte_carlo: MonteCarloBacktestReport | None = None,
    template_name: str | None = None,
) -> list[FailureDiagnosis]:
    diagnoses: list[FailureDiagnosis] = []
    profit_factor = 0 if backtest is None else backtest.profit_factor
    total_return = summary.total_profit_pct

    if summary.trades == 0:
        diagnoses.append(
            FailureDiagnosis(
                category="entry_too_strict",
                severity="high",
                evidence=["Backtest produced zero closed trades."],
                recommendation="Relax entry filters or verify that signal conditions can occur in the tested data.",
            )
        )
        return diagnoses

    if summary.trades >= 20 and summary.win_rate < 0.25:
        diagnoses.append(
            FailureDiagnosis(
                category="entry_too_broad",
                severity="high",
                evidence=[
                    f"Trade sample is {summary.trades}, but win rate is {summary.win_rate:.1%}.",
                    f"Template={template_name or 'unknown'} generated frequent losing entries.",
                ],
                recommendation="Add stricter setup quality filters before entry, such as pullback depth, trend slope, or spread/liquidity confirmation.",
            )
        )

    if summary.trades >= 20 and profit_factor < 0.8:
        diagnoses.append(
            FailureDiagnosis(
                category="payoff_profile_weak",
                severity="high" if profit_factor < 0.6 else "medium",
                evidence=[
                    f"Profit factor is {profit_factor:.3f}.",
                    f"Largest win {summary.largest_win_pct:.3%}, largest loss {summary.largest_loss_pct:.3%}.",
                ],
                recommendation="Redesign exits around asymmetric payoff: cut failed continuation faster or require larger expected move before entry.",
            )
        )

    if total_return < 0 and regime == MarketRegime.RANGING:
        diagnoses.append(
            FailureDiagnosis(
                category="regime_mismatch",
                severity="medium",
                evidence=[f"Strategy lost {total_return:.3%} while classified regime is ranging."],
                recommendation="Block continuation entries in ranging regimes unless trend or volatility expansion is independently confirmed.",
            )
        )

    if monte_carlo is not None and monte_carlo.probability_of_loss >= 0.75:
        diagnoses.append(
            FailureDiagnosis(
                category="monte_carlo_unstable",
                severity="high",
                evidence=[
                    f"Monte Carlo probability of loss is {monte_carlo.probability_of_loss:.1%}.",
                    f"Median simulated return is {monte_carlo.median_return:.3%}.",
                ],
                recommendation="Do not promote; require a new hypothesis or materially different entry/exit design before retesting.",
            )
        )

    expected_return = (signal.rank_score - 50) / 100
    if expected_return > 0 and total_return < 0:
        diagnoses.append(
            FailureDiagnosis(
                category="signal_quality_mismatch",
                severity="medium",
                evidence=[
                    f"Signal rank implied expected return proxy {expected_return:.3%}, realized return was {total_return:.3%}.",
                ],
                recommendation="Treat this signal family as unproven until rank scoring is recalibrated against realized strategy returns.",
            )
        )

    return diagnoses


def _score(value: float) -> float:
    return round(max(0, min(100, value * 100)), 6)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    raise ValueError("trade datetime is required")
