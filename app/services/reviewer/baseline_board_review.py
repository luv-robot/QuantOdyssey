from __future__ import annotations

from uuid import uuid4

from app.models import (
    BaselineBoardReview,
    BaselineImpliedRegimeReport,
    ReviewClaim,
    ReviewQuestion,
    StrategyFamilyBaselineBoard,
    StrategyFamilyBaselineRow,
)


PASSIVE_GROUPS = {"cash", "passive"}


def build_baseline_board_review(
    board: StrategyFamilyBaselineBoard,
    *,
    regime: BaselineImpliedRegimeReport | None = None,
    timeframe_boards: dict[str, StrategyFamilyBaselineBoard] | None = None,
) -> BaselineBoardReview:
    """Turn a baseline board into an inspectable AI-review artifact.

    The review is deliberately evidence-first and numeric. It does not decide
    that a market regime is "true"; it explains what the current baseline set
    implies and where cost-adjusted conclusions are fragile.
    """

    leader = _leader(board)
    active_rows = [row for row in board.rows if row.benchmark_group not in PASSIVE_GROUPS]
    passive_or_cash_leader = leader is not None and leader.benchmark_group in PASSIVE_GROUPS
    positive_gross_negative_net = [
        row for row in active_rows if row.gross_return > 0 and row.total_return <= 0 and row.trades > 0
    ]
    high_cost_drag = [
        row
        for row in active_rows
        if row.cost_drag > max(abs(row.gross_return) * 0.5, 0.05) and row.trades > 0
    ]
    active_net_winners = [row for row in active_rows if row.total_return > 0]
    best_active = max(active_rows, key=lambda item: (item.total_return, item.profit_factor), default=None)
    timeframe_leaders = _timeframe_leaders(timeframe_boards or {})
    findings_ref = f"strategy_family_baseline_board:{board.board_id}:findings"

    evidence_for = [
        ReviewClaim(
            claim_id="baseline_review_cost_adjusted_board",
            claim_type="data_quality",
            statement=(
                "Baseline board reports gross/net returns and explicit cost drag, so strategy-family comparisons "
                "are no longer based on frictionless returns."
            ),
            evidence_refs=[findings_ref],
            severity="medium",
        )
    ]
    if board.is_common_window_aligned:
        evidence_for.append(
            ReviewClaim(
                claim_id="baseline_review_common_window",
                claim_type="test_design",
                statement="Baseline cells are aligned to a common test window, reducing mixed-period distortion.",
                evidence_refs=[f"strategy_family_baseline_board:{board.board_id}:common_window"],
                severity="medium",
            )
        )
    if timeframe_boards:
        evidence_for.append(
            ReviewClaim(
                claim_id="baseline_review_timeframe_boards",
                claim_type="test_design",
                statement=f"Timeframe-separated baseline boards are available for {len(timeframe_boards)} timeframe(s).",
                evidence_refs=[
                    f"strategy_family_baseline_board:{item.board_id}:timeframe_scope"
                    for item in timeframe_boards.values()
                ],
                severity="medium",
            )
        )
    if leader is not None:
        evidence_for.append(
            ReviewClaim(
                claim_id="baseline_review_leader",
                claim_type="performance",
                statement=(
                    f"Current leader is {leader.display_name or leader.strategy_family} with net return "
                    f"{leader.total_return:.4f}, gross return {leader.gross_return:.4f}, and cost drag "
                    f"{leader.cost_drag:.4f}."
                ),
                evidence_refs=[f"strategy_family_baseline_board:{board.board_id}:best_family"],
                severity="medium",
            )
        )

    evidence_against: list[ReviewClaim] = []
    if passive_or_cash_leader:
        evidence_against.append(
            ReviewClaim(
                claim_id="baseline_review_passive_leader",
                claim_type="baseline_advantage",
                statement=(
                    "The best net baseline is passive/cash, so active strategy families have not yet shown a "
                    "generic net edge in this window."
                ),
                evidence_refs=[f"strategy_family_baseline_board:{board.board_id}:rows"],
                severity="high",
            )
        )
    if positive_gross_negative_net:
        names = ", ".join(row.display_name or row.strategy_family for row in positive_gross_negative_net[:4])
        evidence_against.append(
            ReviewClaim(
                claim_id="baseline_review_gross_net_flip",
                claim_type="cost_drag",
                statement=f"{len(positive_gross_negative_net)} active baseline(s) were gross-positive but net-negative: {names}.",
                evidence_refs=[f"strategy_family_baseline_board:{board.board_id}:gross_net"],
                severity="high",
            )
        )
    if high_cost_drag:
        names = ", ".join(row.display_name or row.strategy_family for row in high_cost_drag[:4])
        evidence_against.append(
            ReviewClaim(
                claim_id="baseline_review_high_cost_drag",
                claim_type="cost_drag",
                statement=f"{len(high_cost_drag)} active baseline(s) show large cost drag relative to gross edge: {names}.",
                evidence_refs=[f"strategy_family_baseline_board:{board.board_id}:cost_drag"],
                severity="high",
            )
        )

    blind_spots = []
    if board.cost_model.funding_source == "not_available":
        blind_spots.append(
            ReviewClaim(
                claim_id="baseline_review_funding_blind_spot",
                claim_type="data_gap",
                statement="Funding cost is still a default assumption instead of measured funding history.",
                evidence_refs=[f"strategy_family_baseline_board:{board.board_id}:cost_model"],
                severity="medium",
            )
        )
    if not timeframe_boards:
        blind_spots.append(
            ReviewClaim(
                claim_id="baseline_review_timeframe_blind_spot",
                claim_type="test_design",
                statement="The review only sees an aggregate baseline board; timeframe-specific behavior may be hidden.",
                evidence_refs=[f"strategy_family_baseline_board:{board.board_id}:timeframes"],
                severity="medium",
            )
        )

    ai_questions = [
        ReviewQuestion(
            question_id="baseline_review_question_beta_or_edge",
            question="Is the current opportunity set rewarding passive beta more than active timing?",
            why_it_matters="If yes, new active strategies should be judged against buy-and-hold/DCA first, not cash.",
            evidence_refs=[f"baseline_implied_regime:{regime.report_id}" if regime else findings_ref],
        ),
        ReviewQuestion(
            question_id="baseline_review_question_turnover_budget",
            question="Which candidate families can plausibly survive the current transaction-cost budget?",
            why_it_matters="High-turnover variants can look useful before costs and disappear after netting fees/slippage.",
            evidence_refs=[f"strategy_family_baseline_board:{board.board_id}:cost_drag"],
        ),
    ]

    next_experiments = [
        "Rerun all submitted strategy reviews against net baseline metrics, not frictionless returns.",
        "Compare each active candidate with passive BTC buy-and-hold/DCA over the exact same window.",
        "Bucket baseline winners and laggards by timeframe before optimizing individual strategy parameters.",
    ]
    if positive_gross_negative_net or high_cost_drag:
        next_experiments.append("Prefer lower-turnover variants before spending optimizer budget on high-turnover families.")
    if regime is not None:
        next_experiments.append(f"Treat `{regime.regime_label}` as a provisional reverse-inferred regime and verify it with independent features.")
    if board.cost_model.funding_source == "not_available":
        next_experiments.append("Replace default funding assumptions with measured funding-rate history before judging futures carry-sensitive families.")

    recommended_tasks = [
        "baseline_net_recheck",
        "timeframe_separated_baseline_board",
        "cost_drag_triage",
    ]
    if active_net_winners:
        recommended_tasks.append("active_family_deepening")
    else:
        recommended_tasks.append("generate_lower_turnover_active_baselines")

    scorecard = {
        "leader_family": None if leader is None else leader.strategy_family,
        "leader_is_passive_or_cash": passive_or_cash_leader,
        "leader_net_return": 0 if leader is None else round(leader.total_return, 6),
        "leader_gross_return": 0 if leader is None else round(leader.gross_return, 6),
        "leader_cost_drag": 0 if leader is None else round(leader.cost_drag, 6),
        "active_net_winner_count": len(active_net_winners),
        "active_gross_positive_net_negative_count": len(positive_gross_negative_net),
        "high_cost_drag_active_count": len(high_cost_drag),
        "best_active_family": None if best_active is None else best_active.strategy_family,
        "best_active_net_return": None if best_active is None else round(best_active.total_return, 6),
        "timeframe_leaders": ", ".join(f"{timeframe}:{family}" for timeframe, family in timeframe_leaders.items()),
        "regime_label": None if regime is None else regime.regime_label,
        "regime_confidence": None if regime is None else regime.confidence,
    }

    summary = _summary(leader, passive_or_cash_leader, positive_gross_negative_net, high_cost_drag, regime)
    return BaselineBoardReview(
        review_id=f"baseline_board_review_{uuid4().hex[:8]}",
        source_baseline_board_id=board.board_id,
        source_regime_report_id=None if regime is None else regime.report_id,
        timeframe_scope=board.timeframe_scope,
        leader_family=None if leader is None else leader.strategy_family,
        leader_net_return=0 if leader is None else leader.total_return,
        leader_gross_return=0 if leader is None else leader.gross_return,
        leader_cost_drag=0 if leader is None else leader.cost_drag,
        scorecard=scorecard,
        evidence_for=evidence_for,
        evidence_against=evidence_against,
        blind_spots=blind_spots,
        ai_questions=ai_questions,
        next_experiments=next_experiments,
        recommended_research_tasks=recommended_tasks,
        summary=summary,
    )


def _leader(board: StrategyFamilyBaselineBoard) -> StrategyFamilyBaselineRow | None:
    if board.best_family:
        for row in board.rows:
            if row.strategy_family == board.best_family:
                return row
    return max(board.rows, key=lambda item: (item.total_return, item.profit_factor), default=None)


def _timeframe_leaders(boards: dict[str, StrategyFamilyBaselineBoard]) -> dict[str, str]:
    leaders = {}
    for timeframe, board in sorted(boards.items()):
        leader = _leader(board)
        if leader is not None:
            leaders[timeframe] = leader.strategy_family
    return leaders


def _summary(
    leader: StrategyFamilyBaselineRow | None,
    passive_or_cash_leader: bool,
    positive_gross_negative_net: list[StrategyFamilyBaselineRow],
    high_cost_drag: list[StrategyFamilyBaselineRow],
    regime: BaselineImpliedRegimeReport | None,
) -> str:
    if leader is None:
        return "Baseline review could not identify a leader; data coverage should be checked first."
    regime_text = "" if regime is None else f" The reverse-inferred regime is `{regime.regime_label}`."
    if passive_or_cash_leader:
        base = (
            f"Cost-adjusted baselines currently favor {leader.display_name or leader.strategy_family}; "
            "active families need to beat this passive/cash reference before deeper optimization."
        )
    else:
        base = (
            f"Cost-adjusted baselines currently favor active family {leader.display_name or leader.strategy_family}; "
            "this family is a candidate for deeper validation."
        )
    if positive_gross_negative_net or high_cost_drag:
        base += " Several active rows are materially cost-sensitive, so gross edge should not drive decisions."
    return base + regime_text
