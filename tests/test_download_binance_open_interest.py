from datetime import datetime

from app.models import OpenInterestPoint
from scripts.download_binance_open_interest import download_open_interest


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def fetch_open_interest_history(self, symbol, period, limit, start_time, end_time):
        self.calls.append(
            {
                "symbol": symbol,
                "period": period,
                "limit": limit,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        return [
            OpenInterestPoint(
                symbol=symbol,
                timestamp=datetime(2026, 5, 1),
                open_interest=1000,
                raw={},
            )
        ]


def test_download_open_interest_paginates_and_deduplicates() -> None:
    client = FakeClient()

    points = download_open_interest("BTC/USDT:USDT", period="5m", days=1, limit=100, client=client)

    assert len(points) == 1
    assert client.calls
    assert client.calls[0]["symbol"] == "BTC/USDT:USDT"
    assert client.calls[0]["period"] == "5m"
