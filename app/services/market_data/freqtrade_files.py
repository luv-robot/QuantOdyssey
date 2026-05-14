from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.models import FundingRatePoint, OhlcvCandle, OpenInterestPoint


def load_freqtrade_ohlcv(path: Path, symbol: str, interval: str) -> list[OhlcvCandle]:
    frame = _read_frame(path)
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Freqtrade OHLCV file is missing columns: {sorted(missing)}")
    return [_row_to_candle(row, symbol, interval) for row in frame.to_dict("records")]


def load_freqtrade_funding_rates(path: Path, symbol: str) -> list[FundingRatePoint]:
    frame = _read_frame(path)
    required = {"date", "open"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Freqtrade funding file is missing columns: {sorted(missing)}")
    return [_row_to_funding_rate(row, symbol) for row in frame.to_dict("records")]


def load_open_interest_points(path: Path, symbol: str) -> list[OpenInterestPoint]:
    if path.suffix == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError(f"Open-interest JSON must contain a list: {path}")
        return [_row_to_open_interest(row, symbol) for row in rows]
    frame = _read_frame(path)
    if "date" not in frame.columns and "timestamp" not in frame.columns:
        raise ValueError("Open-interest file must include date or timestamp column.")
    return [_row_to_open_interest(row, symbol) for row in frame.to_dict("records")]


def find_freqtrade_funding_file(ohlcv_path: Path, symbol: str, timeframe: str) -> Path | None:
    base = _freqtrade_file_base(ohlcv_path, symbol, timeframe)
    return _first_existing(
        [
            ohlcv_path.with_name(f"{base}-1h-funding_rate.feather"),
            ohlcv_path.with_name(f"{base}-8h-funding_rate.feather"),
        ]
    )


def find_open_interest_file(ohlcv_path: Path, symbol: str, timeframe: str) -> Path | None:
    base = _freqtrade_file_base(ohlcv_path, symbol, timeframe)
    return _first_existing(
        [
            ohlcv_path.with_name(f"{base}-{timeframe}-open_interest.feather"),
            ohlcv_path.with_name(f"{base}-{timeframe}-open_interest.json"),
            ohlcv_path.with_name(f"{base}-{timeframe}-oi.feather"),
            ohlcv_path.with_name(f"{base}-{timeframe}-oi.json"),
        ]
    )


def _read_frame(path: Path):
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required to read Freqtrade market data files.") from exc
    if path.suffix == ".json":
        return pd.read_json(path)
    return pd.read_feather(path)


def _row_to_candle(row: dict[str, Any], symbol: str, interval: str) -> OhlcvCandle:
    open_time = row["date"].to_pydatetime()
    close_time = open_time + _interval_delta(interval)
    quote_volume = float(row.get("quote_volume") or row["close"] * row["volume"])
    trade_count = int(row.get("trade_count") or 0)
    raw = [
        int(open_time.timestamp() * 1000),
        str(row["open"]),
        str(row["high"]),
        str(row["low"]),
        str(row["close"]),
        str(row["volume"]),
        int(close_time.timestamp() * 1000),
        str(quote_volume),
        trade_count,
    ]
    return OhlcvCandle(
        symbol=symbol.upper(),
        interval=interval,
        open_time=open_time,
        close_time=close_time,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        quote_volume=quote_volume,
        trade_count=trade_count,
        raw=raw,
    )


def _row_to_funding_rate(row: dict[str, Any], symbol: str) -> FundingRatePoint:
    funding_time = row["date"].to_pydatetime()
    return FundingRatePoint(
        symbol=symbol.upper(),
        funding_time=funding_time,
        funding_rate=float(row["open"]),
        mark_price=None,
        raw={
            "date": funding_time.isoformat(),
            "fundingRate": float(row["open"]),
            "source": "freqtrade_funding_rate_feather",
        },
    )


def _row_to_open_interest(row: dict[str, Any], symbol: str) -> OpenInterestPoint:
    timestamp = row.get("date", row.get("timestamp"))
    if hasattr(timestamp, "to_pydatetime"):
        timestamp = timestamp.to_pydatetime()
    elif isinstance(timestamp, (int, float)):
        timestamp = _timestamp_from_number(timestamp)
    elif isinstance(timestamp, str):
        timestamp = _datetime_from_string(timestamp)
    timestamp = _naive_utc(timestamp)
    value = row.get("open_interest", row.get("sumOpenInterest", row.get("open", row.get("close"))))
    if value is None:
        raise ValueError("Open-interest row is missing open_interest/sumOpenInterest/open/close value.")
    return OpenInterestPoint(
        symbol=symbol.upper(),
        timestamp=timestamp,
        open_interest=float(value),
        raw=dict(row),
    )


def _timestamp_from_number(value: int | float):
    divisor = 1000 if value > 10_000_000_000 else 1
    return datetime.utcfromtimestamp(value / divisor)


def _datetime_from_string(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _interval_delta(interval: str) -> timedelta:
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    raise ValueError(f"Unsupported interval: {interval}")


def _freqtrade_file_base(ohlcv_path: Path, symbol: str, timeframe: str) -> str:
    stem = ohlcv_path.stem
    marker = f"-{timeframe}"
    if marker in stem:
        return stem.split(marker, 1)[0]
    return symbol.replace("/", "_").replace(":", "_")


def _first_existing(paths: list[Path]) -> Path | None:
    return next((path for path in paths if path.exists()), None)
