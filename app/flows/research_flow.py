from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.models import MarketSignal, ResearchThesis, StrategyManifest
from app.services.researcher import (
    build_researcher_logs,
    generate_mock_strategy,
    generate_strategy_from_thesis,
)
from app.storage import QuantRepository


def run_research_flow(
    signal: MarketSignal,
    repository: Optional[QuantRepository] = None,
    log_dir: Path = Path("logs/researcher"),
) -> tuple[StrategyManifest, str]:
    manifest, code = generate_mock_strategy(signal, log_dir=log_dir)
    if repository is not None:
        repository.save_strategy(manifest)
        prompt_log, response_log = build_researcher_logs(signal, manifest, code)
        repository.save_prompt_log(prompt_log)
        repository.save_model_response_log(response_log)
    return manifest, code


def run_human_led_research_flow(
    thesis: ResearchThesis,
    signal: MarketSignal,
    repository: Optional[QuantRepository] = None,
    log_dir: Path = Path("logs/researcher"),
) -> tuple[StrategyManifest, str]:
    manifest, code = generate_strategy_from_thesis(thesis, signal, log_dir=log_dir)
    if repository is not None:
        repository.save_research_thesis(thesis)
        repository.save_strategy(manifest)
        prompt_log, response_log = build_researcher_logs(
            signal,
            manifest,
            code,
            model="human-led-agent",
            prompt_version="human_led_strategy_researcher_v1",
            thesis=thesis,
        )
        repository.save_prompt_log(prompt_log)
        repository.save_model_response_log(response_log)
    return manifest, code
