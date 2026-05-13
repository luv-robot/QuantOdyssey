from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Optional
from urllib.parse import urlencode
from urllib.request import urlopen

from app.models import (
    FundingRatePoint,
    OhlcvCandle,
    OpenInterestPoint,
    OrderBookLevel,
    OrderBookSnapshot,
)

Transport = Callable[[str], Any]


class BinanceMarketDataClient:
    def __init__(
        self,
        spot_base_url: str = "https://api.binance.com",
        futures_base_url: str = "https://fapi.binance.com",
        transport: Optional[Transport] = None,
    ) -> None:
        self.spot_base_url = spot_base_url.rstrip("/")
        self.futures_base_url = futures_base_url.rstrip("/")
        self.transport = transport or self._default_transport

    def fetch_ohlcv(
        self,
        symbol: str,
        interval: str = "5m",
        limit: int = 120,
    ) -> list[OhlcvCandle]:
        payload = self._get(
            self.spot_base_url,
            "/api/v3/klines",
            {"symbol": _api_symbol(symbol), "interval": interval, "limit": limit},
        )
        return [_parse_kline(symbol, interval, row) for row in payload]

    def fetch_funding_rate(self, symbol: str, limit: int = 24) -> list[FundingRatePoint]:
        payload = self._get(
            self.futures_base_url,
            "/fapi/v1/fundingRate",
            {"symbol": _api_symbol(symbol), "limit": limit},
        )
        return [_parse_funding_rate(symbol, row) for row in payload]

    def fetch_open_interest(self, symbol: str) -> OpenInterestPoint:
        payload = self._get(
            self.futures_base_url,
            "/fapi/v1/openInterest",
            {"symbol": _api_symbol(symbol)},
        )
        return _parse_open_interest(symbol, payload)

    def fetch_orderbook(self, symbol: str, limit: int = 100) -> OrderBookSnapshot:
        payload = self._get(
            self.spot_base_url,
            "/api/v3/depth",
            {"symbol": _api_symbol(symbol), "limit": limit},
        )
        return _parse_orderbook(symbol, payload)

    def _get(self, base_url: str, path: str, params: dict[str, Any]) -> Any:
        url = f"{base_url}{path}?{urlencode(params)}"
        return self.transport(url)

    @staticmethod
    def _default_transport(url: str) -> Any:
        with urlopen(url, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))


def _api_symbol(symbol: str) -> str:
    return symbol.replace("/", "").upper()


def _dt_from_ms(value: int | str) -> datetime:
    return datetime.utcfromtimestamp(int(value) / 1000)


def _parse_kline(symbol: str, interval: str, row: list[Any]) -> OhlcvCandle:
    return OhlcvCandle(
        symbol=symbol.upper(),
        interval=interval,
        open_time=_dt_from_ms(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        close_time=_dt_from_ms(row[6]),
        quote_volume=float(row[7]),
        trade_count=int(row[8]),
        raw=row,
    )


def _parse_funding_rate(symbol: str, row: dict[str, Any]) -> FundingRatePoint:
    return FundingRatePoint(
        symbol=symbol.upper(),
        funding_time=_dt_from_ms(row["fundingTime"]),
        funding_rate=float(row["fundingRate"]),
        mark_price=float(row["markPrice"]) if row.get("markPrice") is not None else None,
        raw=row,
    )


def _parse_open_interest(symbol: str, row: dict[str, Any]) -> OpenInterestPoint:
    return OpenInterestPoint(
        symbol=symbol.upper(),
        timestamp=_dt_from_ms(row["time"]),
        open_interest=float(row["openInterest"]),
        raw=row,
    )


def _parse_orderbook(symbol: str, row: dict[str, Any]) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol=symbol.upper(),
        captured_at=datetime.utcnow(),
        last_update_id=int(row["lastUpdateId"]),
        bids=[OrderBookLevel(price=float(price), quantity=float(qty)) for price, qty in row["bids"]],
        asks=[OrderBookLevel(price=float(price), quantity=float(qty)) for price, qty in row["asks"]],
        raw=row,
    )
