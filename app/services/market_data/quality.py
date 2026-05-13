from __future__ import annotations

from datetime import datetime, timedelta

from app.models import DataQualityFlag, DataQualityReport, MarketSignal


def audit_market_signal_quality(
    signal: MarketSignal,
    max_signal_age: timedelta = timedelta(days=2),
) -> DataQualityReport:
    flags: list[DataQualityFlag] = []
    details: list[str] = []

    if not signal.data_sources:
        flags.append(DataQualityFlag.MISSING_DATA)
        details.append("Signal has no declared data sources.")
    if not signal.features:
        flags.append(DataQualityFlag.MISSING_DATA)
        details.append("Signal has no feature snapshot.")

    signal_age = datetime.utcnow() - signal.created_at.replace(tzinfo=None)
    if signal_age > max_signal_age:
        flags.append(DataQualityFlag.STALE_DATA)
        details.append(f"Signal is older than {max_signal_age}.")

    volume_zscore = float(signal.features.get("volume_zscore", 0) or 0)
    funding_rate = float(signal.features.get("funding_rate", 0) or 0)
    if abs(volume_zscore) > 12 or abs(funding_rate) > 0.01:
        flags.append(DataQualityFlag.OUTLIER)
        details.append("Signal contains an extreme volume or funding feature.")

    return DataQualityReport(
        dataset_id=f"signal_quality_{signal.signal_id}",
        is_usable=not flags,
        flags=list(dict.fromkeys(flags)),
        details=details or ["MarketSignal passed basic quality checks."],
    )
