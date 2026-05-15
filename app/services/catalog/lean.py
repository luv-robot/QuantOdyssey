from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from uuid import uuid4

from app.models import (
    EvaluationType,
    StrategyCatalogItem,
    StrategyCatalogLanguage,
    StrategyCatalogReport,
    StrategyCatalogSource,
    StrategyFamily,
    StrategyMigrationDifficulty,
)


LEAN_REPO_URL = "https://github.com/QuantConnect/Lean"


def build_lean_strategy_catalog(
    lean_root: Path,
    *,
    repo_url: str = LEAN_REPO_URL,
    max_files: int | None = None,
    include_regression: bool = True,
) -> tuple[StrategyCatalogReport, list[StrategyCatalogItem]]:
    files = _lean_algorithm_files(lean_root, include_regression=include_regression)
    if max_files is not None:
        files = files[:max_files]
    items = [_catalog_item_from_file(path, lean_root, repo_url) for path in files]
    language_counts = Counter(item.language.value for item in items)
    family_counts = Counter(item.strategy_family.value for item in items)
    difficulty_counts = Counter(item.migration_difficulty.value for item in items)
    role_counts: Counter[str] = Counter()
    for item in items:
        role_counts.update(item.suggested_roles)

    report = StrategyCatalogReport(
        report_id=f"lean_strategy_catalog_{uuid4().hex[:8]}",
        source=StrategyCatalogSource.QUANTCONNECT_LEAN,
        source_repo_url=repo_url,
        scanned_paths=[str(_relative(path, lean_root)) for path in files],
        total_files_scanned=len(files),
        item_count=len(items),
        language_counts=dict(sorted(language_counts.items())),
        family_counts=dict(sorted(family_counts.items())),
        difficulty_counts=dict(sorted(difficulty_counts.items())),
        suggested_role_counts=dict(sorted(role_counts.items())),
        item_ids=[item.item_id for item in items],
        findings=_catalog_findings(items),
    )
    return report, items


def _lean_algorithm_files(lean_root: Path, *, include_regression: bool) -> list[Path]:
    search_roots = [lean_root / "Algorithm.Python", lean_root / "Algorithm.CSharp"]
    files: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        for pattern in ("*.py", "*.cs"):
            for path in root.rglob(pattern):
                if path.name.startswith("_"):
                    continue
                if not include_regression and "Regression" in path.name:
                    continue
                files.append(path)
    return sorted(files, key=lambda item: str(item).lower())


def _catalog_item_from_file(path: Path, lean_root: Path, repo_url: str) -> StrategyCatalogItem:
    text = path.read_text(encoding="utf-8", errors="ignore")
    relative_path = _relative(path, lean_root)
    language = StrategyCatalogLanguage.PYTHON if path.suffix == ".py" else StrategyCatalogLanguage.CSHARP
    class_names = _class_names(text, language)
    name = class_names[0] if class_names else path.stem
    asset_classes = _asset_classes(text)
    data_requirements = _data_requirements(text)
    indicators = _indicators(text)
    resolutions = _resolutions(text)
    universe_features = _universe_features(text)
    family = _strategy_family(text, indicators)
    evaluation_type = _evaluation_type(text, family)
    difficulty, notes = _migration_difficulty(
        language=language,
        asset_classes=asset_classes,
        data_requirements=data_requirements,
        universe_features=universe_features,
    )
    roles = _suggested_roles(difficulty, family, asset_classes, data_requirements)
    tags = sorted(
        dict.fromkeys(
            [
                *asset_classes,
                *data_requirements,
                *indicators,
                *universe_features,
                language.value,
                difficulty.value,
            ]
        )
    )
    return StrategyCatalogItem(
        item_id=_item_id(relative_path, text),
        source=StrategyCatalogSource.QUANTCONNECT_LEAN,
        source_repo_url=repo_url,
        source_path=str(relative_path),
        language=language,
        name=name,
        class_names=class_names,
        strategy_family=family,
        evaluation_type=evaluation_type,
        asset_classes=asset_classes,
        data_requirements=data_requirements,
        indicators=indicators,
        resolutions=resolutions,
        universe_features=universe_features,
        suggested_roles=roles,
        migration_difficulty=difficulty,
        migration_notes=notes,
        tags=tags,
    )


def _class_names(text: str, language: StrategyCatalogLanguage) -> list[str]:
    if language == StrategyCatalogLanguage.PYTHON:
        return re.findall(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text, flags=re.MULTILINE)
    return re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\b", text)


def _asset_classes(text: str) -> list[str]:
    lower = text.lower()
    mapping = {
        "crypto": ["addcrypto", "crypto", "btcusd", "ethusd"],
        "equity": ["addequity", "equity", "spy"],
        "forex": ["addforex", "forex", "eurusd"],
        "future": ["addfuture", "futurechain", "futureschain", "futures"],
        "option": ["addoption", "optionchain", "options"],
        "cfd": ["addcfd", "cfd"],
    }
    return _matches(lower, mapping)


def _data_requirements(text: str) -> list[str]:
    lower = text.lower()
    requirements = ["ohlcv"] if any(token in lower for token in ["addcrypto", "addequity", "addforex", "addfuture", "addoption", "history("]) else []
    mapping = {
        "fundamental": ["fundamental", "coarsefundamental", "finefundamental", "adduniverse"],
        "option_chain": ["optionchain", "addoption", "optioncontract"],
        "future_chain": ["futurechain", "addfuture", "futureschain"],
        "custom_data": ["pythondata", "basedata", "custom data", "quandl", "nasdaqdata"],
        "universe_selection": ["adduniverse", "universe.selection", "coarse", "fine"],
        "scheduled_events": ["schedule.on", "date_rules", "time_rules"],
        "portfolio_framework": ["alphamodel", "portfolioconstruction", "riskmanagementmodel", "executionmodel"],
    }
    return sorted(dict.fromkeys([*requirements, *_matches(lower, mapping)]))


def _indicators(text: str) -> list[str]:
    lower = text.lower()
    mapping = {
        "rsi": ["rsi(", "relativestrengthindex"],
        "macd": ["macd(", "movingaverageconvergencedivergence"],
        "ema": ["ema(", "exponentialmovingaverage"],
        "sma": ["sma(", "simplemovingaverage"],
        "bollinger": ["bb(", "bollinger"],
        "atr": ["atr(", "averagetruerange"],
        "adx": ["adx(", "averagedirectionalindex"],
        "vwap": ["vwap"],
        "momentum": ["mom(", "momentum"],
        "roc": ["roc(", "rateofchange"],
    }
    return _matches(lower, mapping)


def _resolutions(text: str) -> list[str]:
    lower = text.lower()
    resolutions = []
    for name in ["tick", "second", "minute", "hour", "daily"]:
        if f"resolution.{name}" in lower or f"resolution::{name}" in lower:
            resolutions.append(name)
    return resolutions


def _universe_features(text: str) -> list[str]:
    lower = text.lower()
    mapping = {
        "coarse_universe": ["coarsefundamental", "coarse"],
        "fine_universe": ["finefundamental", "fine"],
        "manual_universe": ["adduniverse"],
        "scheduled_rebalance": ["schedule.on", "date_rules", "time_rules"],
        "framework_algorithm": ["alphamodel", "portfolioconstruction", "riskmanagementmodel", "executionmodel"],
    }
    return _matches(lower, mapping)


def _strategy_family(text: str, indicators: list[str]) -> StrategyFamily:
    lower = text.lower()
    if any(token in lower for token in ["meanreversion", "mean reversion", "bollinger"]) or "rsi" in indicators:
        return StrategyFamily.VWAP_EXHAUSTION_REVERSION
    if any(token in lower for token in ["momentum", "ema", "sma", "macd", "trend"]) or any(
        item in indicators for item in ["ema", "sma", "macd", "momentum", "roc"]
    ):
        return StrategyFamily.CONTINUOUS_TREND_OR_MOMENTUM
    if any(token in lower for token in ["breakout", "channel"]):
        return StrategyFamily.FAILED_BREAKOUT_PUNISHMENT
    return StrategyFamily.GENERAL_OR_UNKNOWN


def _evaluation_type(text: str, family: StrategyFamily) -> EvaluationType:
    lower = text.lower()
    if any(token in lower for token in ["optionchain", "earnings", "event", "rebalance"]):
        return EvaluationType.EVENT_DRIVEN_ALPHA
    if family in {
        StrategyFamily.CONTINUOUS_TREND_OR_MOMENTUM,
        StrategyFamily.VWAP_EXHAUSTION_REVERSION,
        StrategyFamily.GENERAL_OR_UNKNOWN,
    }:
        return EvaluationType.CONTINUOUS_ALPHA
    return EvaluationType.EVENT_DRIVEN_ALPHA


def _migration_difficulty(
    *,
    language: StrategyCatalogLanguage,
    asset_classes: list[str],
    data_requirements: list[str],
    universe_features: list[str],
) -> tuple[StrategyMigrationDifficulty, list[str]]:
    notes: list[str] = []
    hard_features = {"option", "future"} & set(asset_classes)
    hard_data = {"option_chain", "future_chain", "custom_data", "portfolio_framework"} & set(data_requirements)
    if language == StrategyCatalogLanguage.CSHARP:
        notes.append("C# algorithms require translation or Lean-native execution.")
    if hard_features:
        notes.append("Derivative asset classes are not portable to the current Freqtrade-only runtime.")
    if hard_data:
        notes.append("Requires Lean-native data or framework features beyond OHLCV.")
    if universe_features:
        notes.append("Universe selection must be modeled explicitly before migration.")

    if language == StrategyCatalogLanguage.CSHARP or hard_features or hard_data:
        return StrategyMigrationDifficulty.HIGH, notes
    if universe_features or ("equity" in asset_classes and "crypto" not in asset_classes):
        notes.append("May be useful as a baseline archetype but not directly runnable on crypto data.")
        return StrategyMigrationDifficulty.MEDIUM, notes
    notes.append("OHLCV/indicator pattern may be portable as a Freqtrade baseline or sample.")
    return StrategyMigrationDifficulty.LOW, notes


def _suggested_roles(
    difficulty: StrategyMigrationDifficulty,
    family: StrategyFamily,
    asset_classes: list[str],
    data_requirements: list[str],
) -> list[str]:
    roles = ["sample_strategy"]
    if difficulty == StrategyMigrationDifficulty.LOW:
        roles.append("baseline_candidate")
    if family != StrategyFamily.GENERAL_OR_UNKNOWN:
        roles.append("strategy_family_template")
    if difficulty == StrategyMigrationDifficulty.HIGH or "portfolio_framework" in data_requirements:
        roles.append("agent_eval_case")
    if "crypto" in asset_classes:
        roles.append("crypto_porting_candidate")
    return roles


def _catalog_findings(items: list[StrategyCatalogItem]) -> list[str]:
    if not items:
        return ["No Lean algorithms were found under Algorithm.Python or Algorithm.CSharp."]
    low_count = sum(1 for item in items if item.migration_difficulty == StrategyMigrationDifficulty.LOW)
    baseline_count = sum(1 for item in items if "baseline_candidate" in item.suggested_roles)
    high_count = sum(1 for item in items if item.migration_difficulty == StrategyMigrationDifficulty.HIGH)
    return [
        f"Cataloged {len(items)} Lean algorithm file(s).",
        f"{baseline_count} item(s) are plausible baseline candidates after review.",
        f"{low_count} item(s) appear mechanically portable to Freqtrade-style OHLCV strategies.",
        f"{high_count} item(s) should stay Lean-native or be used as agent eval/reference material.",
        "Catalog items are research samples, not validated alpha.",
    ]


def _matches(lower_text: str, mapping: dict[str, list[str]]) -> list[str]:
    return sorted(
        key
        for key, needles in mapping.items()
        if any(needle.lower() in lower_text for needle in needles)
    )


def _item_id(relative_path: Path, text: str) -> str:
    digest = hashlib.sha256(f"{relative_path}:{text[:4000]}".encode("utf-8")).hexdigest()[:12]
    stem = re.sub(r"[^a-z0-9]+", "_", relative_path.stem.lower()).strip("_")[:48]
    return f"lean_{stem}_{digest}"


def _relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path
