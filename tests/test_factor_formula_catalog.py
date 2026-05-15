from app.models import (
    FactorEvaluationScope,
    FactorImplementationStatus,
    StrategyFamily,
)
from app.services.catalog import build_worldquant_style_factor_catalog
from app.storage import QuantRepository


def test_worldquant_style_catalog_marks_portable_and_cross_sectional_factors() -> None:
    report, items = build_worldquant_style_factor_catalog()

    assert report.total_items >= 10
    assert report.baseline_candidate_count >= 5
    assert any(item.implementation_status == FactorImplementationStatus.PORTABLE_OHLCV for item in items)
    assert any(item.evaluation_scope == FactorEvaluationScope.CROSS_SECTIONAL_UNIVERSE for item in items)
    assert all("no third-party code is copied" in item.license_note for item in items)


def test_worldquant_style_catalog_contains_funding_extension() -> None:
    _, items = build_worldquant_style_factor_catalog()

    funding_item = next(item for item in items if item.factor_id == "wq_style_funding_augmented_reversal")
    assert funding_item.strategy_family == StrategyFamily.FUNDING_CROWDING_FADE
    assert "funding_rate" in funding_item.required_fields
    assert funding_item.implementation_status == FactorImplementationStatus.NEEDS_EXTRA_DATA


def test_repository_persists_factor_formula_catalog() -> None:
    report, items = build_worldquant_style_factor_catalog()
    repository = QuantRepository()

    repository.save_factor_formula_catalog_report(report)
    for item in items:
        repository.save_factor_formula_item(item)

    assert repository.get_factor_formula_catalog_report(report.report_id) == report
    assert repository.get_factor_formula_item(items[0].factor_id) == items[0]
    portable = repository.query_factor_formula_items(implementation_status="portable_ohlcv")
    assert portable
    assert all(item.implementation_status == FactorImplementationStatus.PORTABLE_OHLCV for item in portable)
