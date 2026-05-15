from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.models import ResearchScratchpadEvent, ResearchScratchpadRun, ScratchpadEventType


DEFAULT_SCRATCHPAD_DIR = Path(".qo") / "scratchpad"


def create_scratchpad_run(
    *,
    run_id: str,
    purpose: str,
    base_dir: Path | str = DEFAULT_SCRATCHPAD_DIR,
) -> ResearchScratchpadRun:
    path = _scratchpad_path(base_dir, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    return ResearchScratchpadRun(run_id=run_id, purpose=purpose, scratchpad_path=str(path))


def append_scratchpad_event(
    *,
    run_id: str,
    event_type: ScratchpadEventType,
    payload: dict,
    base_dir: Path | str = DEFAULT_SCRATCHPAD_DIR,
    task_id: str | None = None,
    thesis_id: str | None = None,
    strategy_id: str | None = None,
    evidence_refs: list[str] | None = None,
) -> ResearchScratchpadEvent:
    event = ResearchScratchpadEvent(
        event_id=f"scratch_{run_id}_{uuid4().hex[:8]}",
        run_id=run_id,
        event_type=event_type,
        payload=payload,
        task_id=task_id,
        thesis_id=thesis_id,
        strategy_id=strategy_id,
        evidence_refs=evidence_refs or [],
    )
    path = _scratchpad_path(base_dir, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(event.model_dump_json() + "\n")
    return event


def read_scratchpad_events(
    *,
    run_id: str,
    base_dir: Path | str = DEFAULT_SCRATCHPAD_DIR,
) -> list[ResearchScratchpadEvent]:
    path = _scratchpad_path(base_dir, run_id)
    if not path.exists():
        return []
    events: list[ResearchScratchpadEvent] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                events.append(ResearchScratchpadEvent.model_validate(json.loads(stripped)))
    return events


def _scratchpad_path(base_dir: Path | str, run_id: str) -> Path:
    safe_run_id = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in run_id)
    return Path(base_dir) / f"{safe_run_id}.jsonl"
