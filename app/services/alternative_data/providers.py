from __future__ import annotations

from typing import Protocol

from app.models import AlternativeDataMetric, AlternativeDataProvider


class AlternativeDataClient(Protocol):
    provider: AlternativeDataProvider

    def fetch_metric(
        self,
        metric_id: str,
        symbol: str | None = None,
        **params: str,
    ) -> AlternativeDataMetric:
        """Fetch a single provider metric for thesis evidence."""


class StubAlternativeDataClient:
    def __init__(self, provider: AlternativeDataProvider) -> None:
        self.provider = provider

    def fetch_metric(
        self,
        metric_id: str,
        symbol: str | None = None,
        **params: str,
    ) -> AlternativeDataMetric:
        return AlternativeDataMetric(
            provider=self.provider,
            metric_id=metric_id,
            symbol=symbol,
            value=0.0,
            tags=params,
            raw={
                "stub": True,
                "note": "Provider API integration is intentionally deferred until credentials exist.",
            },
        )


class GlassnodeClient(StubAlternativeDataClient):
    def __init__(self) -> None:
        super().__init__(AlternativeDataProvider.GLASSNODE)


class NansenClient(StubAlternativeDataClient):
    def __init__(self) -> None:
        super().__init__(AlternativeDataProvider.NANSEN)
