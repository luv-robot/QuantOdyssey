from __future__ import annotations

from typing import Optional

from app.models import ReviewCase


class InMemoryReviewStore:
    def __init__(self) -> None:
        self._cases: dict[str, ReviewCase] = {}

    def add(self, review_case: ReviewCase) -> ReviewCase:
        self._cases[review_case.case_id] = review_case
        return review_case

    def query(
        self,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        result: Optional[str] = None,
        signal_type: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> list[ReviewCase]:
        del signal_type, symbol
        cases = list(self._cases.values())
        if signal_id is not None:
            cases = [case for case in cases if case.signal_id == signal_id]
        if strategy_id is not None:
            cases = [case for case in cases if case.strategy_id == strategy_id]
        if result is not None:
            cases = [case for case in cases if case.result.value == result]
        return cases
