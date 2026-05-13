from tests.test_models import sample_manifest

from app.services.risk_auditor import audit_strategy_code


def test_auditor_rejects_missing_stoploss() -> None:
    code = """
class UnsafeStrategy:
    timeframe = "5m"
"""

    result = audit_strategy_code(code, sample_manifest())

    assert result.approved is False
    assert {finding.rule_id for finding in result.findings} == {"STOPLOSS_REQUIRED"}


def test_auditor_rejects_martingale_and_lookahead() -> None:
    code = """
class UnsafeStrategy:
    timeframe = "5m"
    stoploss = -0.1

    def populate_entry_trend(self, dataframe, metadata):
        dataframe["future"] = dataframe["close"].shift(-1)
        martingale = True
        return dataframe
"""

    result = audit_strategy_code(code, sample_manifest())

    assert result.approved is False
    assert "MARTINGALE" in {finding.rule_id for finding in result.findings}
    assert ".SHIFT(-" in {finding.rule_id for finding in result.findings}


def test_auditor_approves_basic_safe_strategy() -> None:
    code = """
class SafeStrategy:
    timeframe = "5m"
    stoploss = -0.08
"""

    result = audit_strategy_code(code, sample_manifest())

    assert result.approved is True
    assert result.findings == []
