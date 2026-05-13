from __future__ import annotations

from typing import Optional

from app.models import MarketSignal
from app.services.scout import (
    filter_ranked_signals,
    generate_funding_oi_extreme_signal,
    generate_volume_spike_signal,
)
from app.storage import QuantRepository


def run_scout_flow(
    min_rank: int = 70,
    repository: Optional[QuantRepository] = None,
) -> list[MarketSignal]:
    signals = filter_ranked_signals(
        [
            generate_volume_spike_signal(),
            generate_funding_oi_extreme_signal(),
            generate_volume_spike_signal(signal_id="signal_low_rank_001", rank_score=45),
        ],
        min_rank=min_rank,
    )

    if repository is not None:
        for signal in signals:
            repository.save_signal(signal)

    return signals
