from __future__ import annotations

import re
from uuid import uuid4

from app.models import (
    DataSufficiencyLevel,
    EvaluationType,
    EventEpisode,
    EventEpisodeStage,
    MarketSignal,
    PreReviewQuestion,
    PreReviewQuestionCategory,
    PreReviewStatus,
    ResearchDesignDraft,
    ResearchThesis,
    StrategyFamily,
    ThesisPreReview,
)


COMMON_INDICATORS = {
    "rsi",
    "macd",
    "ema",
    "sma",
    "bollinger",
    "布林",
    "均线",
    "adx",
    "atr",
    "vwap",
    "kdj",
}
COMMON_PATTERNS = {
    "breakout",
    "突破",
    "放量",
    "volume",
    "trend",
    "趋势",
    "momentum",
    "动量",
    "reversal",
    "反转",
    "mean reversion",
    "均值回归",
    "超买",
    "超卖",
}
VAGUE_TERMS = {
    "strong",
    "weak",
    "high",
    "low",
    "fast",
    "slow",
    "quickly",
    "明显",
    "较强",
    "较弱",
    "放量",
    "缩量",
    "突破",
    "趋势",
    "回调",
    "很快",
    "极端",
    "大幅",
}
MECHANISM_DATA_TERMS = {
    "funding": DataSufficiencyLevel.L1_FUNDING_OI,
    "资金费率": DataSufficiencyLevel.L1_FUNDING_OI,
    "open interest": DataSufficiencyLevel.L1_FUNDING_OI,
    "oi": DataSufficiencyLevel.L1_FUNDING_OI,
    "持仓": DataSufficiencyLevel.L1_FUNDING_OI,
    "orderbook": DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION,
    "订单簿": DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION,
    "liquidation": DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION,
    "清算": DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION,
    "链上": DataSufficiencyLevel.L3_ONCHAIN_NARRATIVE,
    "nansen": DataSufficiencyLevel.L3_ONCHAIN_NARRATIVE,
    "glassnode": DataSufficiencyLevel.L3_ONCHAIN_NARRATIVE,
    "wallet": DataSufficiencyLevel.L3_ONCHAIN_NARRATIVE,
}


def build_thesis_pre_review(thesis: ResearchThesis) -> ThesisPreReview:
    text = _thesis_text(thesis)
    missing = _missing_structure(thesis)
    completeness_score = max(0, 100 - len(missing) * 14)
    clarity_findings = _clarity_findings(text)
    condition_clarity_score = max(15, 100 - len(clarity_findings) * 15)
    commonness_findings = _commonness_findings(text)
    commonness_risk_score = min(100, 20 + len(commonness_findings) * 20)
    questions = _build_questions(missing, clarity_findings, commonness_findings, text)
    status = _status_from_scores(completeness_score, condition_clarity_score, questions)
    return ThesisPreReview(
        pre_review_id=f"pre_{thesis.thesis_id}_{uuid4().hex[:8]}",
        thesis_id=thesis.thesis_id,
        status=status,
        completeness_score=round(completeness_score, 2),
        condition_clarity_score=round(condition_clarity_score, 2),
        commonness_risk_score=round(commonness_risk_score, 2),
        structure_findings=[
            f"Missing or weak structure field: {item}." for item in missing
        ]
        or ["Thesis includes the minimum structure required for a first research design."],
        clarity_findings=clarity_findings
        or ["Entry, exit, and invalidation language is clear enough for a first draft."],
        commonness_findings=commonness_findings
        or ["No obvious indicator-stacking or highly common public-template pattern was detected."],
        questions=questions,
        assumptions_if_proceed=_assumptions_if_proceed(thesis, missing, clarity_findings),
        unresolved_questions=[question.question for question in questions],
        hypothesis_drift_risk=_hypothesis_drift_risk(thesis, clarity_findings),
        evidence_refs=_evidence_refs(thesis, commonness_findings),
    )


def build_research_design_draft(
    thesis: ResearchThesis,
    pre_review: ThesisPreReview,
) -> ResearchDesignDraft:
    text = _thesis_text(thesis)
    family = _infer_strategy_family(text)
    evaluation_type = _evaluation_type_for_family(family)
    target_data_level = _infer_data_sufficiency_level(text)
    validation_data_level = _infer_validation_data_sufficiency_level(text, target_data_level)
    missing_evidence = _missing_evidence_for_levels(validation_data_level, target_data_level)
    return ResearchDesignDraft(
        design_id=f"design_{thesis.thesis_id}_{uuid4().hex[:8]}",
        thesis_id=thesis.thesis_id,
        pre_review_id=pre_review.pre_review_id,
        thesis_summary=_summarize_thesis(thesis),
        inferred_strategy_family=family,
        evaluation_type=evaluation_type,
        data_sufficiency_level=target_data_level,
        validation_data_sufficiency_level=validation_data_level,
        missing_evidence=missing_evidence,
        event_definition_draft=_event_definition_for_family(family),
        baseline_set=_baseline_set_for_evaluation_type(evaluation_type),
        required_data=_required_data_for_level(validation_data_level),
        what_this_tests=_what_this_tests(family, validation_data_level),
        what_this_does_not_test=_what_this_does_not_test(validation_data_level, missing_evidence),
        ai_assumptions=pre_review.assumptions_if_proceed,
        unresolved_questions=pre_review.unresolved_questions,
        proceed_recommendation=pre_review.status,
    )


def build_event_episode(
    thesis: ResearchThesis,
    signal: MarketSignal,
    design: ResearchDesignDraft,
) -> EventEpisode:
    text = _thesis_text(thesis)
    direction = "short" if any(term in text for term in ["做空", "short", "crowded longs"]) else "long_or_mixed"
    missing_evidence = _event_missing_evidence(signal, design)
    validation_level = (
        DataSufficiencyLevel.L0_OHLCV_ONLY
        if "historical_open_interest" in missing_evidence
        else design.validation_data_sufficiency_level
    )
    return EventEpisode(
        event_id=f"event_{thesis.thesis_id}_{signal.signal_id}_{uuid4().hex[:8]}",
        thesis_id=thesis.thesis_id,
        signal_id=signal.signal_id,
        strategy_family=design.inferred_strategy_family,
        evaluation_type=design.evaluation_type,
        stage=EventEpisodeStage.SETUP,
        direction=direction,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        setup_window_bars=_setup_window_bars(signal.timeframe),
        trigger_window_bars=_trigger_window_bars(text),
        data_sufficiency_level=design.data_sufficiency_level,
        validation_data_sufficiency_level=validation_level,
        trigger_definition=design.event_definition_draft,
        features=dict(signal.features),
        missing_evidence=missing_evidence,
    )


def _thesis_text(thesis: ResearchThesis) -> str:
    parts = [
        thesis.title,
        thesis.market_observation,
        thesis.hypothesis,
        thesis.trade_logic,
        " ".join(thesis.expected_regimes),
        " ".join(thesis.invalidation_conditions),
        " ".join(thesis.constraints),
    ]
    return " ".join(parts).lower()


def _event_missing_evidence(signal: MarketSignal, design: ResearchDesignDraft) -> list[str]:
    missing = list(design.missing_evidence)
    if signal.features.get("open_interest_source") == "volume_proxy":
        missing.append("historical_open_interest")
    return sorted(set(missing))


def _missing_structure(thesis: ResearchThesis) -> list[str]:
    missing = []
    if _is_weak(thesis.market_observation):
        missing.append("market_observation")
    if _is_weak(thesis.hypothesis):
        missing.append("hypothesis")
    if _is_weak(thesis.trade_logic):
        missing.append("trade_logic")
    if not thesis.expected_regimes or all(_is_weak(item) for item in thesis.expected_regimes):
        missing.append("expected_regimes")
    if not thesis.invalidation_conditions or all(
        _is_weak(item) for item in thesis.invalidation_conditions
    ):
        missing.append("invalidation_conditions")
    if not any(word in thesis.trade_logic.lower() for word in ["stop", "止损", "exit", "出场"]):
        missing.append("exit_or_stop_logic")
    return missing


def _is_weak(value: str) -> bool:
    return len(value.strip()) < 12


def _clarity_findings(text: str) -> list[str]:
    findings = []
    vague_hits = sorted(term for term in VAGUE_TERMS if term in text)
    has_numeric_definition = any(char.isdigit() for char in text) or any(
        token in text for token in ["atr", "%", "percentile", "zscore", "bar", "candle", "根"]
    )
    if vague_hits and not has_numeric_definition:
        findings.append(
            "Several condition words are directionally useful but not yet testable: "
            + ", ".join(vague_hits[:5])
            + "."
        )
    if "entry" not in text and "enter" not in text and "入场" not in text:
        findings.append("Entry trigger is not explicitly separated from the market thesis.")
    if "exit" not in text and "stop" not in text and "出场" not in text and "止损" not in text:
        findings.append("Exit or stop condition is not explicit enough to audit.")
    if "invalid" not in text and "失效" not in text and "fails" not in text:
        findings.append("Invalidation language is present only weakly or not at all.")
    return findings[:4]


def _commonness_findings(text: str) -> list[str]:
    indicator_hits = sorted(token for token in COMMON_INDICATORS if _term_in_text(token, text))
    pattern_hits = sorted(token for token in COMMON_PATTERNS if _term_in_text(token, text))
    findings = []
    if len(indicator_hits) >= 2:
        findings.append(
            "The thesis references multiple common indicators: "
            + ", ".join(indicator_hits[:5])
            + ". This may become indicator stacking unless each filter has a separate role."
        )
    if len(pattern_hits) >= 2:
        findings.append(
            "The thesis is close to common public strategy language: "
            + ", ".join(pattern_hits[:5])
            + ". The differentiating edge should be made explicit."
        )
    if "rsi" in indicator_hits and ("macd" in indicator_hits or "ema" in indicator_hits):
        findings.append(
            "RSI combined with MACD/EMA is a common retail template; baseline comparison should be strict."
        )
    return findings[:4]


def _term_in_text(term: str, text: str) -> bool:
    if any("\u4e00" <= char <= "\u9fff" for char in term):
        return term in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text) is not None


def _build_questions(
    missing: list[str],
    clarity_findings: list[str],
    commonness_findings: list[str],
    text: str,
) -> list[PreReviewQuestion]:
    questions: list[PreReviewQuestion] = []
    if missing:
        questions.append(
            PreReviewQuestion(
                category=PreReviewQuestionCategory.COMPLETENESS,
                question=(
                    "Which missing structure should define the experiment first: "
                    + ", ".join(missing[:3])
                    + "?"
                ),
                why_it_matters="Without this, the system may test a different idea from the one you intend.",
            )
        )
    if clarity_findings:
        questions.append(
            PreReviewQuestion(
                category=PreReviewQuestionCategory.CLARITY,
                question="Which exact thresholds, lookback windows, or confirmation candles define the key entry setup?",
                why_it_matters="Ambiguous words like strong, breakout, or quick reversal cannot be reproduced reliably.",
            )
        )
    if commonness_findings:
        questions.append(
            PreReviewQuestion(
                category=PreReviewQuestionCategory.COMMONNESS,
                question="What is the intended edge beyond a common public indicator/template strategy?",
                why_it_matters="If the edge is not distinct, backtest gains are more likely to come from overfitting or market beta.",
                blocks_design_quality=False,
            )
        )
    if any(term in text for term in ["taker", "cvd", "orderbook", "订单簿", "liquidation", "清算"]):
        questions.append(
            PreReviewQuestion(
                category=PreReviewQuestionCategory.DATA,
                question="Which advanced data fields are available now, and which should be replaced by OHLCV/funding/OI proxies in the first test?",
                why_it_matters="The thesis references orderflow or liquidation-style evidence that cannot be proven from OHLCV alone.",
                blocks_design_quality=False,
            )
        )
    if any(term in text for term in ["long", "short", "做多", "做空"]) and any(
        term in text for term in ["对称", "both", "双向"]
    ):
        questions.append(
            PreReviewQuestion(
                category=PreReviewQuestionCategory.CLARITY,
                question="Should the first experiment test both long and short sides, or isolate one side to avoid mixing two mechanisms?",
                why_it_matters="Long and short crowding can have different sample counts, payoff shapes, and failure modes.",
                blocks_design_quality=False,
            )
        )
    if any(term in text for term in ["event_count", "trade_count", "事件", "样本"]):
        questions.append(
            PreReviewQuestion(
                category=PreReviewQuestionCategory.CLARITY,
                question="What is the minimum event and trade sample required before you consider the evidence mature enough?",
                why_it_matters="Low-frequency event strategies should not be judged like always-on strategies.",
                blocks_design_quality=False,
            )
        )
    return questions[:8]


def _status_from_scores(
    completeness_score: float,
    condition_clarity_score: float,
    questions: list[PreReviewQuestion],
) -> PreReviewStatus:
    if completeness_score >= 80 and condition_clarity_score >= 70 and not questions:
        return PreReviewStatus.READY_FOR_DESIGN
    if completeness_score < 65 or condition_clarity_score < 55:
        return PreReviewStatus.NEEDS_CLARIFICATION
    return PreReviewStatus.CAN_PROCEED_WITH_ASSUMPTIONS


def _assumptions_if_proceed(
    thesis: ResearchThesis,
    missing: list[str],
    clarity_findings: list[str],
) -> list[str]:
    assumptions = []
    if "exit_or_stop_logic" in missing:
        assumptions.append("Use a conservative fixed stoploss and simple momentum/timeout exit for the first draft.")
    if clarity_findings:
        assumptions.append("Translate vague setup language into simple OHLCV thresholds for the first test.")
    if not thesis.constraints:
        assumptions.append("Assume no leverage escalation and no exchange-side execution logic.")
    return assumptions


def _hypothesis_drift_risk(thesis: ResearchThesis, clarity_findings: list[str]) -> str:
    logic = thesis.trade_logic.lower()
    hypothesis = thesis.hypothesis.lower()
    shared_terms = set(logic.split()) & set(hypothesis.split())
    if len(shared_terms) <= 2 or len(clarity_findings) >= 3:
        return "high"
    if clarity_findings:
        return "medium"
    return "low"


def _evidence_refs(thesis: ResearchThesis, commonness_findings: list[str]) -> list[str]:
    refs = [
        f"thesis:{thesis.thesis_id}:market_observation",
        f"thesis:{thesis.thesis_id}:hypothesis",
        f"thesis:{thesis.thesis_id}:trade_logic",
    ]
    if commonness_findings:
        refs.append("pre_review:common_public_strategy_heuristics")
    return refs


def _infer_strategy_family(text: str) -> StrategyFamily:
    if any(term in text for term in ["funding", "资金费率", "basis", "基差"]):
        return StrategyFamily.FUNDING_CROWDING_FADE
    if any(term in text for term in ["liquidation", "清算", "cascade", "瀑布"]):
        return StrategyFamily.LIQUIDATION_CASCADE_REVERSAL
    if any(term in text for term in ["fake breakout", "failed breakout", "假突破", "突破失败"]):
        return StrategyFamily.FAILED_BREAKOUT_PUNISHMENT
    if any(term in text for term in ["sweep", "扫", "插针", "wick", "影线"]):
        return StrategyFamily.LIQUIDITY_SWEEP_REVERSAL
    if any(term in text for term in ["trend trap", "趋势陷阱", "continuation", "延续"]):
        return StrategyFamily.TREND_TRAP_CONTINUATION
    if any(term in text for term in ["vwap"]):
        return StrategyFamily.VWAP_EXHAUSTION_REVERSION
    if any(term in text for term in ["trend", "趋势", "momentum", "动量", "ema"]):
        return StrategyFamily.CONTINUOUS_TREND_OR_MOMENTUM
    return StrategyFamily.GENERAL_OR_UNKNOWN


def _evaluation_type_for_family(family: StrategyFamily) -> EvaluationType:
    if family in {
        StrategyFamily.LIQUIDITY_SWEEP_REVERSAL,
        StrategyFamily.LIQUIDATION_CASCADE_REVERSAL,
        StrategyFamily.FUNDING_CROWDING_FADE,
        StrategyFamily.FAILED_BREAKOUT_PUNISHMENT,
        StrategyFamily.EVENT_OVERREACTION_FADE,
        StrategyFamily.TREND_TRAP_CONTINUATION,
        StrategyFamily.VWAP_EXHAUSTION_REVERSION,
    }:
        return EvaluationType.EVENT_DRIVEN_ALPHA
    return EvaluationType.CONTINUOUS_ALPHA


def _infer_data_sufficiency_level(text: str) -> DataSufficiencyLevel:
    level = DataSufficiencyLevel.L0_OHLCV_ONLY
    rank = {
        DataSufficiencyLevel.L0_OHLCV_ONLY: 0,
        DataSufficiencyLevel.L1_FUNDING_OI: 1,
        DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION: 2,
        DataSufficiencyLevel.L3_ONCHAIN_NARRATIVE: 3,
    }
    for term, required_level in MECHANISM_DATA_TERMS.items():
        if term in text and rank[required_level] > rank[level]:
            level = required_level
    return level


def _infer_validation_data_sufficiency_level(
    text: str,
    target_level: DataSufficiencyLevel,
) -> DataSufficiencyLevel:
    if any(term in text for term in ["first test data level = l1", "第一轮按 l1", "l1 ohlcv + funding + oi"]):
        return DataSufficiencyLevel.L1_FUNDING_OI
    if any(term in text for term in ["first test data level = l0", "ohlcv only", "仅 ohlcv"]):
        return DataSufficiencyLevel.L0_OHLCV_ONLY
    return target_level


def _missing_evidence_for_levels(
    validation_level: DataSufficiencyLevel,
    target_level: DataSufficiencyLevel,
) -> list[str]:
    validation_data = set(_required_data_for_level(validation_level))
    target_data = set(_required_data_for_level(target_level))
    missing = sorted(target_data - validation_data)
    if target_level == DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION and validation_level == DataSufficiencyLevel.L1_FUNDING_OI:
        missing.extend(["cvd", "taker_flow", "price_impact_per_aggressive_volume"])
    return list(dict.fromkeys(missing))


def _summarize_thesis(thesis: ResearchThesis) -> str:
    return (
        f"{thesis.title}: observe '{thesis.market_observation[:160]}', test whether "
        f"'{thesis.hypothesis[:160]}' can be implemented through '{thesis.trade_logic[:160]}'."
    )


def _event_definition_for_family(family: StrategyFamily) -> str:
    definitions = {
        StrategyFamily.FAILED_BREAKOUT_PUNISHMENT: (
            "Detect a break beyond an N-bar high/low, weak acceptance, and close back inside the prior range."
        ),
        StrategyFamily.LIQUIDITY_SWEEP_REVERSAL: (
            "Detect price trading beyond a recent swing level, wick rejection, and reclaim within a short window."
        ),
        StrategyFamily.FUNDING_CROWDING_FADE: (
            "Detect extreme funding/open-interest crowding plus failure to extend in the crowded direction."
        ),
        StrategyFamily.TREND_TRAP_CONTINUATION: (
            "Detect high trend score, failed countertrend pullback, and continuation-level reclaim."
        ),
        StrategyFamily.CONTINUOUS_TREND_OR_MOMENTUM: (
            "Detect repeated trend or momentum conditions over rolling OHLCV windows."
        ),
    }
    return definitions.get(family, "Draft a simple reproducible setup from the thesis before strategy generation.")


def _baseline_set_for_evaluation_type(evaluation_type: EvaluationType) -> list[str]:
    if evaluation_type == EvaluationType.EVENT_DRIVEN_ALPHA:
        return ["no_trade", "naive_event_entry", "randomized_event_window", "opposite_direction"]
    return ["no_trade", "buy_and_hold", "simple_momentum", "random_entry_same_frequency"]


def _required_data_for_level(level: DataSufficiencyLevel) -> list[str]:
    data = ["ohlcv"]
    if level in {
        DataSufficiencyLevel.L1_FUNDING_OI,
        DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION,
        DataSufficiencyLevel.L3_ONCHAIN_NARRATIVE,
    }:
        data.extend(["funding_rate", "open_interest"])
    if level in {DataSufficiencyLevel.L2_ORDERFLOW_LIQUIDATION, DataSufficiencyLevel.L3_ONCHAIN_NARRATIVE}:
        data.extend(["orderbook", "liquidation"])
    if level == DataSufficiencyLevel.L3_ONCHAIN_NARRATIVE:
        data.extend(["onchain_or_wallet_flow", "narrative_or_event_data"])
    return data


def _what_this_tests(family: StrategyFamily, level: DataSufficiencyLevel) -> list[str]:
    return [
        f"Whether the inferred {family.value} setup has repeatable behavior under available data.",
        f"Whether first-pass evidence is usable at {level.value}.",
        "Whether the idea survives basic baseline and robustness checks.",
    ]


def _what_this_does_not_test(
    level: DataSufficiencyLevel,
    missing_evidence: list[str] | None = None,
) -> list[str]:
    missing_evidence = missing_evidence or []
    if level == DataSufficiencyLevel.L0_OHLCV_ONLY:
        return [
            "It does not prove real crowding, forced flow, liquidation pressure, or orderbook absorption.",
            "It only tests an OHLCV proxy for the stated mechanism.",
        ]
    if level == DataSufficiencyLevel.L1_FUNDING_OI:
        notes = ["It does not directly prove orderbook absorption or actual liquidation cascades."]
        if missing_evidence:
            notes.append("Missing future evidence: " + ", ".join(missing_evidence) + ".")
        return notes
    return ["It does not make investment or live execution decisions."]


def _setup_window_bars(timeframe: str) -> int:
    if timeframe.endswith("m"):
        minutes = int(timeframe[:-1])
        return max(1, int((24 * 60) / minutes))
    return 24


def _trigger_window_bars(text: str) -> int:
    match = re.search(r"(\d+)\s*(?:根|bar|bars|k)", text)
    if match:
        return max(1, int(match.group(1)))
    return 3
