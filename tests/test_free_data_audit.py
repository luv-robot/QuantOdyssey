from pathlib import Path

from scripts.audit_free_data_sources import _local_history_report, _normalize_pair_for_mode


def test_normalize_pair_for_mode() -> None:
    assert _normalize_pair_for_mode("BTC/USDT:USDT", "spot") == "BTC/USDT"
    assert _normalize_pair_for_mode("BTC/USDT", "futures") == "BTC/USDT:USDT"


def test_local_history_report_checks_spot_and_futures_files(tmp_path) -> None:
    userdir = tmp_path / "user_data"
    spot_file = userdir / "data" / "binance" / "BTC_USDT-5m.feather"
    futures_file = userdir / "data" / "binance" / "futures" / "BTC_USDT_USDT-5m-futures.feather"
    spot_file.parent.mkdir(parents=True)
    futures_file.parent.mkdir(parents=True)
    spot_file.write_text("", encoding="utf-8")
    futures_file.write_text("", encoding="utf-8")
    spot_config = tmp_path / "spot.json"
    futures_config = tmp_path / "futures.json"
    spot_config.write_text('{"trading_mode": "spot"}', encoding="utf-8")
    futures_config.write_text('{"trading_mode": "futures"}', encoding="utf-8")

    report = _local_history_report(
        pairs=["BTC/USDT"],
        timeframes=["5m"],
        spot_config=spot_config,
        futures_config=futures_config,
        userdir=userdir,
        timerange="20240101-20260501",
    )

    assert [item["ok"] for item in report] == [True, True]
    assert Path(report[0]["data_checks"][0]["found_path"]).name == "BTC_USDT-5m.feather"
    assert Path(report[1]["data_checks"][0]["found_path"]).name == "BTC_USDT_USDT-5m-futures.feather"
