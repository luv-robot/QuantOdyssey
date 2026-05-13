from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    retry_delay_seconds: int = 0


DEFAULT_MVP_RETRY_POLICY = RetryPolicy(max_attempts=1, retry_delay_seconds=0)
