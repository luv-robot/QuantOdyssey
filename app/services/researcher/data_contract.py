from __future__ import annotations

import re
from datetime import datetime
from uuid import uuid4

from app.models import (
    MarketSignal,
    ResearchThesis,
    SignalType,
    ThesisDataContract,
    ThesisDataContractStatus,
)


DATA_ALIASES = {
    "ohlcv": ["ohlcv", "kline", "candles", "candle", "bar", "日线", "k线"],
    "funding": ["funding", "资金费率"],
    "open_interest": ["open interest", "open_interest", "oi", "持仓"],
    "orderflow": ["orderflow", "taker", "cvd", "主动买", "主动卖"],
    "orderbook": ["orderbook", "订单簿", "depth", "spread"],
    "tick": ["tick", "逐笔", "trade tape"],
    "liquidation": ["liquidation", "清算", "爆仓"],
    "onchain": ["onchain", "链上", "nansen", "glassnode", "wallet"],
}


def build_thesis_data_contract(
    thesis: ResearchThesis,
    signal: MarketSignal | None,
) -> ThesisDataContract:
    requested_timeframe = preferred_timeframe_from_thesis(thesis)
    requested_data = requested_data_from_thesis(thesis)
    requested_side = requested_side_from_thesis(thesis)
    signal_sources = [] if signal is None else list(signal.data_sources)
    mismatches: list[str] = []
    warnings: list[str] = []

    if signal is None:
        if requested_timeframe or requested_data:
            status = ThesisDataContractStatus.NEEDS_THESIS_SEED
            action = "Create a thesis-seed data context before running strategy tests."
        else:
            status = ThesisDataContractStatus.BLOCKED
            action = "Select a MarketSignal or declare at least a timeframe/data requirement."
            mismatches.append("No MarketSignal or thesis data requirement was available.")
        return ThesisDataContract(
            contract_id=f"contract_{thesis.thesis_id}_{uuid4().hex[:8]}",
            thesis_id=thesis.thesis_id,
            status=status,
            can_run=status == ThesisDataContractStatus.NEEDS_THESIS_SEED,
            requested_timeframe=requested_timeframe,
            requested_data=requested_data,
            requested_side=requested_side,
            mismatches=mismatches,
            warnings=warnings,
            recommended_action=action,
        )

    if requested_timeframe and requested_timeframe != signal.timeframe:
        mismatches.append(
            f"Thesis requests timeframe `{requested_timeframe}`, but selected MarketSignal is `{signal.timeframe}`."
        )

    available_data = _available_data_from_sources(signal_sources)
    missing_data = [
        item
        for item in requested_data
        if item not in available_data and not (item == "ohlcv" and _source_has_ohlcv(signal_sources))
    ]
    if missing_data:
        mismatches.append(
            "Selected MarketSignal is missing required data: " + ", ".join(missing_data) + "."
        )

    if requested_side == "long_only" and _signal_looks_short_biased(signal):
        warnings.append(
            "Thesis is long-only, while the selected signal appears short-biased. Use only as evidence, not execution context."
        )
    if requested_side == "short_only" and _signal_looks_long_biased(signal):
        warnings.append(
            "Thesis is short-only, while the selected signal appears long-biased. Use only as evidence, not execution context."
        )

    status = ThesisDataContractStatus.COMPATIBLE if not mismatches else ThesisDataContractStatus.BLOCKED
    action = (
        "Run pipeline with the selected MarketSignal."
        if status == ThesisDataContractStatus.COMPATIBLE
        else "Use a compatible MarketSignal or create a thesis-seed data context."
    )
    return ThesisDataContract(
        contract_id=f"contract_{thesis.thesis_id}_{signal.signal_id}_{uuid4().hex[:8]}",
        thesis_id=thesis.thesis_id,
        signal_id=signal.signal_id,
        status=status,
        can_run=not mismatches,
        requested_timeframe=requested_timeframe,
        requested_data=requested_data,
        requested_side=requested_side,
        signal_timeframe=signal.timeframe,
        signal_data_sources=signal_sources,
        signal_type=signal.signal_type.value,
        mismatches=mismatches,
        warnings=warnings,
        recommended_action=action,
    )


def build_thesis_seed_signal(
    thesis: ResearchThesis,
    source_signal: MarketSignal | None = None,
) -> MarketSignal:
    timeframe = preferred_timeframe_from_thesis(thesis, fallback=None) or (
        source_signal.timeframe if source_signal is not None else "1h"
    )
    requested_data = requested_data_from_thesis(thesis) or ["ohlcv"]
    symbol = _preferred_symbol_from_thesis(thesis) or (
        source_signal.symbol if source_signal is not None else "BTC/USDT:USDT"
    )
    exchange = source_signal.exchange if source_signal is not None else "binance"
    signal_id = f"signal_thesis_seed_{thesis.thesis_id}_{timeframe}_{uuid4().hex[:8]}"
    source_features = (
        {
            "source_signal_id": source_signal.signal_id,
            "source_signal_timeframe": source_signal.timeframe,
            "source_signal_type": source_signal.signal_type.value,
        }
        if source_signal is not None
        else {}
    )
    return MarketSignal(
        signal_id=signal_id,
        created_at=datetime.utcnow(),
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        signal_type=SignalType.THESIS_SEED,
        rank_score=50,
        features={
            "thesis_seed": True,
            "requested_timeframe": timeframe,
            "requested_data": ",".join(requested_data),
            "liquidity_score": 1.0,
            **source_features,
        },
        hypothesis=(
            "Thesis-seed context created from user-declared data requirements. "
            "It must be validated against real data availability before trusting results."
        ),
        data_sources=[f"thesis_seed:required:{item}:{timeframe}" for item in requested_data],
    )


def select_compatible_signal(
    thesis: ResearchThesis,
    signals: list[MarketSignal],
) -> tuple[MarketSignal | None, ThesisDataContract | None]:
    best_warning: tuple[MarketSignal, ThesisDataContract] | None = None
    for signal in signals:
        contract = build_thesis_data_contract(thesis, signal)
        if contract.can_run:
            if not contract.warnings:
                return signal, contract
            if best_warning is None:
                best_warning = (signal, contract)
    return best_warning if best_warning is not None else (None, None)


def preferred_timeframe_from_thesis(thesis: ResearchThesis, fallback: str | None = None) -> str | None:
    text = _thesis_text(thesis)
    explicit = re.search(r"(?:timeframe|周期|级别)\s*[:：=]\s*([0-9]+\s*[mhdw])", text)
    if explicit:
        return explicit.group(1).replace(" ", "")
    if re.search(r"\b([0-9]+)\s*(?:day|days|d)\b", text):
        match = re.search(r"\b([0-9]+)\s*(?:day|days|d)\b", text)
        return f"{match.group(1)}d" if match else fallback
    for token, timeframe in [
        ("daily", "1d"),
        ("日线", "1d"),
        ("4h", "4h"),
        ("1h", "1h"),
        ("15m", "15m"),
        ("5m", "5m"),
        ("5分钟", "5m"),
        ("分钟线", "5m"),
    ]:
        if token in text:
            return timeframe
    return fallback


def requested_data_from_thesis(thesis: ResearchThesis) -> list[str]:
    text = _thesis_text(thesis)
    requested = []
    for canonical, aliases in DATA_ALIASES.items():
        if any(alias in text for alias in aliases):
            requested.append(canonical)
    if "daily ohlcv" in text or "日线" in text:
        requested.append("ohlcv")
    return sorted(dict.fromkeys(requested))


def requested_side_from_thesis(thesis: ResearchThesis) -> str | None:
    text = _thesis_text(thesis)
    if any(term in text for term in ["long-only", "long only", "只做多", "仅做多"]):
        return "long_only"
    if any(term in text for term in ["short-only", "short only", "只做空", "仅做空"]):
        return "short_only"
    return None


def draft_thesis_fields_from_notes(notes: str) -> dict[str, str]:
    cleaned = notes.strip()
    if not cleaned:
        return {}
    title = _first_markdown_title(cleaned) or _short_title(cleaned)
    return {
        "title": title,
        "market_observation": _section_or_default(cleaned, ["市场观察", "observation"], cleaned),
        "hypothesis": _section_or_default(cleaned, ["假设", "hypothesis"], cleaned),
        "trade_logic": _section_or_default(cleaned, ["交易逻辑", "trade logic", "logic"], cleaned),
        "expected_regimes": _section_or_default(cleaned, ["适用市场", "适用", "regime"], "unspecified"),
        "invalidation_conditions": _section_or_default(cleaned, ["失效条件", "invalidation"], "needs explicit invalidation"),
        "constraints": _constraints_from_notes(cleaned),
    }


def _thesis_text(thesis: ResearchThesis) -> str:
    return " ".join(
        [
            thesis.title,
            thesis.market_observation,
            thesis.hypothesis,
            thesis.trade_logic,
            " ".join(thesis.expected_regimes),
            " ".join(thesis.invalidation_conditions),
            " ".join(thesis.constraints),
        ]
    ).lower()


def _available_data_from_sources(sources: list[str]) -> set[str]:
    text = " ".join(sources).lower()
    available = set()
    for canonical, aliases in DATA_ALIASES.items():
        if any(alias in text for alias in aliases):
            available.add(canonical)
    if "open_interest" in text:
        available.add("open_interest")
    return available


def _source_has_ohlcv(sources: list[str]) -> bool:
    return any("ohlcv" in source.lower() or "candle" in source.lower() for source in sources)


def _signal_looks_short_biased(signal: MarketSignal) -> bool:
    text = " ".join([signal.signal_type.value, signal.hypothesis, " ".join(signal.data_sources)]).lower()
    return "funding_oi_extreme" in text or "short" in text or "crowded long" in text


def _signal_looks_long_biased(signal: MarketSignal) -> bool:
    text = " ".join([signal.signal_type.value, signal.hypothesis, " ".join(signal.data_sources)]).lower()
    return "crowded short" in text or "long" in text


def _preferred_symbol_from_thesis(thesis: ResearchThesis) -> str | None:
    text = _thesis_text(thesis)
    for base in ["btc", "eth", "sol", "bnb", "xrp", "doge"]:
        if re.search(rf"(?<![a-z0-9]){base}(?![a-z0-9])", text):
            return f"{base.upper()}/USDT:USDT"
    return None


def _first_markdown_title(notes: str) -> str | None:
    for line in notes.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title[:80]
    return None


def _short_title(notes: str) -> str:
    words = re.findall(r"[A-Za-z0-9_\-/]+|[\u4e00-\u9fff]+", notes)
    return " ".join(words[:8])[:80] or "Untitled Research Thesis"


def _section_or_default(notes: str, headings: list[str], default: str) -> str:
    lower_lines = notes.splitlines()
    for index, line in enumerate(lower_lines):
        normalized = line.strip().strip("#").strip().lower()
        if any(heading in normalized for heading in headings):
            collected = []
            for next_line in lower_lines[index + 1 :]:
                if next_line.strip().startswith("#") and collected:
                    break
                if next_line.strip():
                    collected.append(next_line.strip())
                if len(" ".join(collected)) > 600:
                    break
            if collected:
                return "\n".join(collected)[:1200]
    return default[:1200]


def _constraints_from_notes(notes: str) -> str:
    constraints = []
    text = notes.lower()
    timeframe = preferred_timeframe_from_thesis(
        ResearchThesis(
            thesis_id="draft",
            title="draft",
            market_observation=notes,
            hypothesis=notes,
            trade_logic=notes,
            expected_regimes=["draft"],
            invalidation_conditions=["draft"],
        )
    )
    if timeframe:
        constraints.append(f"timeframe: {timeframe}")
    data = requested_data_from_thesis(
        ResearchThesis(
            thesis_id="draft",
            title="draft",
            market_observation=notes,
            hypothesis=notes,
            trade_logic=notes,
            expected_regimes=["draft"],
            invalidation_conditions=["draft"],
        )
    )
    if data:
        constraints.append("required_data: " + ", ".join(data))
    if "long-only" in text or "long only" in text or "只做多" in text:
        constraints.append("long-only")
    if "short-only" in text or "short only" in text or "只做空" in text:
        constraints.append("short-only")
    if "stop" in text or "止损" in text:
        constraints.append("must define stoploss")
    return "\n".join(dict.fromkeys(constraints))
