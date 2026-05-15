from datetime import datetime

from app.flows.human_research_pipeline import run_human_research_pipeline
from app.models import (
    MarketSignal,
    MonteCarloBacktestConfig,
    ResearchThesis,
    SignalType,
    ThesisDataContractStatus,
    ThesisStatus,
)
from app.services.researcher import (
    build_thesis_data_contract,
    build_thesis_seed_signal,
    draft_thesis_fields_from_notes,
    generate_thesis_strategy_candidates,
)
from app.storage import QuantRepository


def _daily_rsi_thesis() -> ResearchThesis:
    return ResearchThesis(
        thesis_id="thesis_daily_rsi",
        title="RSI divergences (1d)",
        status=ThesisStatus.READY_FOR_IMPLEMENTATION,
        market_observation="BTC daily RSI divergences may mark exhaustion.",
        hypothesis="Daily bullish divergence can lead to a long-only mean reversion bounce.",
        trade_logic="Enter long after RSI divergence confirmation and exit on invalidation or stoploss.",
        expected_regimes=["daily mean reversion"],
        invalidation_conditions=["RSI divergence fails and price makes a lower low"],
        constraints=["timeframe: 1d", "required_data: daily OHLCV", "long-only", "must define stoploss"],
    )


def _funding_signal() -> MarketSignal:
    return MarketSignal(
        signal_id="signal_funding_5m",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=82,
        features={"funding_percentile_30d": 95, "open_interest_percentile_30d": 80},
        hypothesis="Funding and OI crowding may fade.",
        data_sources=["freqtrade:futures_ohlcv:BTC/USDT:USDT:5m", "funding", "historical_open_interest"],
    )


def test_data_contract_blocks_timeframe_mismatch() -> None:
    contract = build_thesis_data_contract(_daily_rsi_thesis(), _funding_signal())

    assert contract.status == ThesisDataContractStatus.BLOCKED
    assert not contract.can_run
    assert contract.requested_timeframe == "1d"
    assert contract.signal_timeframe == "5m"
    assert any("timeframe" in item for item in contract.mismatches)


def test_thesis_seed_signal_honors_declared_timeframe_and_data() -> None:
    thesis = _daily_rsi_thesis()
    seed = build_thesis_seed_signal(thesis, source_signal=_funding_signal())
    contract = build_thesis_data_contract(thesis, seed)

    assert seed.signal_type == SignalType.THESIS_SEED
    assert seed.timeframe == "1d"
    assert "ohlcv" in ",".join(seed.data_sources).lower()
    assert contract.status == ThesisDataContractStatus.COMPATIBLE
    assert contract.can_run


def test_strategy_candidates_use_thesis_timeframe_over_signal_timeframe() -> None:
    candidates = generate_thesis_strategy_candidates(_daily_rsi_thesis(), _funding_signal(), count=1)

    assert candidates[0].manifest.timeframe == "1d"
    assert "timeframe = \"1d\"" in candidates[0].strategy_code


def test_pipeline_replaces_incompatible_signal_with_thesis_seed(tmp_path) -> None:
    repository = QuantRepository()
    result = run_human_research_pipeline(
        _daily_rsi_thesis(),
        _funding_signal(),
        repository,
        candidate_count=1,
        monte_carlo_config=MonteCarloBacktestConfig(simulations=20, horizon_trades=10),
        backtest_mode="mock",
        strategy_dir=tmp_path,
    )

    assert result.signal.signal_type == SignalType.THESIS_SEED
    assert result.signal.timeframe == "1d"
    assert result.event_episode.timeframe == "1d"
    assert result.event_episode.direction == "long"
    assert result.data_contract.can_run
    assert result.data_contract.warnings
    saved_contracts = repository.query_thesis_data_contracts(thesis_id="thesis_daily_rsi")
    assert len(saved_contracts) == 1
    assert saved_contracts[0].signal_id == result.signal.signal_id


def test_thesis_notes_create_structured_draft_constraints() -> None:
    draft = draft_thesis_fields_from_notes(
        """
        # RSI divergences (1d)
        Market observation: BTC daily RSI divergences may mark exhaustion.
        Hypothesis: bullish divergence can lead to a long-only bounce.
        Trade logic: enter long after confirmation, must define stoploss.
        timeframe: 1d
        required_data: daily OHLCV
        long-only
        """
    )

    assert draft["title"] == "RSI divergences (1d)"
    assert "timeframe: 1d" in draft["constraints"]
    assert "required_data: ohlcv" in draft["constraints"]
    assert "long-only" in draft["constraints"]
