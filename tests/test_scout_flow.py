from app.flows import run_scout_flow
from app.services.scout import filter_ranked_signals, generate_volume_spike_signal
from app.storage import QuantRepository


def test_scout_filters_low_rank_signals_and_persists_results() -> None:
    repository = QuantRepository()

    signals = run_scout_flow(min_rank=70, repository=repository)

    assert {signal.signal_id for signal in signals} == {
        "signal_volume_spike_001",
        "signal_funding_oi_001",
    }
    assert repository.get_signal("signal_volume_spike_001") == signals[0]
    assert repository.get_signal("signal_low_rank_001") is None


def test_rank_filter_keeps_only_minimum_score() -> None:
    signals = [
        generate_volume_spike_signal(signal_id="low", rank_score=69),
        generate_volume_spike_signal(signal_id="high", rank_score=70),
    ]

    assert [signal.signal_id for signal in filter_ranked_signals(signals, min_rank=70)] == ["high"]
