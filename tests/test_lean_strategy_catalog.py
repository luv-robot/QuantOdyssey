from pathlib import Path

from app.models import StrategyCatalogLanguage, StrategyMigrationDifficulty, StrategyFamily
from app.services.catalog import build_lean_strategy_catalog
from app.storage import QuantRepository


def test_lean_catalog_extracts_portable_python_baseline_candidate(tmp_path: Path) -> None:
    python_dir = tmp_path / "Algorithm.Python"
    python_dir.mkdir()
    (python_dir / "RsiCryptoAlgorithm.py").write_text(
        """
class RsiCryptoAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2021, 1, 1)
        self.btc = self.AddCrypto("BTCUSD", Resolution.Daily).Symbol
        self.rsi = self.RSI(self.btc, 14, MovingAverageType.Wilders, Resolution.Daily)

    def OnData(self, data):
        if self.rsi.Current.Value < 30:
            self.SetHoldings(self.btc, 1)
""",
        encoding="utf-8",
    )

    report, items = build_lean_strategy_catalog(tmp_path)

    assert report.item_count == 1
    item = items[0]
    assert item.language == StrategyCatalogLanguage.PYTHON
    assert item.name == "RsiCryptoAlgorithm"
    assert item.asset_classes == ["crypto"]
    assert "ohlcv" in item.data_requirements
    assert "rsi" in item.indicators
    assert "daily" in item.resolutions
    assert item.strategy_family == StrategyFamily.VWAP_EXHAUSTION_REVERSION
    assert item.migration_difficulty == StrategyMigrationDifficulty.LOW
    assert "baseline_candidate" in item.suggested_roles


def test_lean_catalog_marks_csharp_options_as_high_difficulty(tmp_path: Path) -> None:
    csharp_dir = tmp_path / "Algorithm.CSharp"
    csharp_dir.mkdir()
    (csharp_dir / "OptionChainAlgorithm.cs").write_text(
        """
public class OptionChainAlgorithm : QCAlgorithm
{
    public override void Initialize()
    {
        AddOption("SPY", Resolution.Minute);
    }
    public override void OnData(Slice data) {}
}
""",
        encoding="utf-8",
    )

    _, items = build_lean_strategy_catalog(tmp_path)

    assert items[0].language == StrategyCatalogLanguage.CSHARP
    assert "option" in items[0].asset_classes
    assert "option_chain" in items[0].data_requirements
    assert items[0].migration_difficulty == StrategyMigrationDifficulty.HIGH
    assert "agent_eval_case" in items[0].suggested_roles


def test_repository_persists_strategy_catalog_items_and_reports(tmp_path: Path) -> None:
    python_dir = tmp_path / "Algorithm.Python"
    python_dir.mkdir()
    (python_dir / "EmaAlgorithm.py").write_text(
        """
class EmaAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.spy = self.AddEquity("SPY", Resolution.Hour).Symbol
        self.ema = self.EMA(self.spy, 20, Resolution.Hour)
""",
        encoding="utf-8",
    )
    report, items = build_lean_strategy_catalog(tmp_path)
    repository = QuantRepository()

    repository.save_strategy_catalog_report(report)
    for item in items:
        repository.save_strategy_catalog_item(item)

    assert repository.get_strategy_catalog_report(report.report_id) == report
    assert repository.get_strategy_catalog_item(items[0].item_id) == items[0]
    assert repository.query_strategy_catalog_items(language="python") == [items[0]]
    assert repository.query_strategy_catalog_reports(source="quantconnect_lean") == [report]
