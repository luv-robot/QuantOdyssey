from __future__ import annotations

import os
from pathlib import Path

from app.models import (
    BacktestCostModel,
    BacktestReport,
    BacktestStatus,
    CrossSymbolValidationReport,
    RealBacktestValidationSuiteReport,
    StrategyManifest,
    SymbolValidationResult,
)
from app.services.backtester.costs import default_backtest_cost_model_from_env
from app.services.backtester.freqtrade_cli import run_freqtrade_backtest


DEFAULT_RELATED_SYMBOLS = ["ETH/USDT", "SOL/USDT", "BNB/USDT"]
DEFAULT_STRESS_SYMBOLS = ["DOGE/USDT", "XRP/USDT", "ADA/USDT"]
DEFAULT_WALK_FORWARD_RANGES = ["20210101-20220101", "20220101-20230101", "20230101-20240101"]


def run_real_validation_suite(
    manifest: StrategyManifest,
    source_backtest: BacktestReport,
    primary_symbol: str,
    related_symbols: list[str] | None = None,
    stress_symbols: list[str] | None = None,
    walk_forward_ranges: list[str] | None = None,
    out_of_sample_timerange: str | None = None,
    config_path: Path | None = None,
    userdir: Path | None = None,
    timeout_seconds: int | None = None,
    cost_model: BacktestCostModel | None = None,
) -> tuple[
    RealBacktestValidationSuiteReport,
    BacktestReport | None,
    list[BacktestReport],
    BacktestReport | None,
    CrossSymbolValidationReport,
]:
    config_path = config_path or Path(os.getenv("FREQTRADE_CONFIG", "configs/freqtrade_config.json"))
    userdir = userdir or Path(os.getenv("FREQTRADE_USER_DATA", "freqtrade_user_data"))
    timeout_seconds = timeout_seconds or int(os.getenv("FREQTRADE_BACKTEST_TIMEOUT", "600"))
    resolved_cost_model = cost_model or default_backtest_cost_model_from_env()
    related_symbols = related_symbols or _symbols_from_env("FREQTRADE_RELATED_PAIRS", DEFAULT_RELATED_SYMBOLS)
    stress_symbols = stress_symbols or _symbols_from_env("FREQTRADE_STRESS_PAIRS", DEFAULT_STRESS_SYMBOLS)
    walk_forward_ranges = walk_forward_ranges or _symbols_from_env(
        "FREQTRADE_WALK_FORWARD_RANGES",
        DEFAULT_WALK_FORWARD_RANGES,
    )
    out_of_sample_timerange = out_of_sample_timerange or os.getenv(
        "FREQTRADE_OOS_TIMERANGE",
        "20240101-20260501",
    )

    findings: list[str] = []
    out_of_sample = _run_window(
        manifest,
        timerange=out_of_sample_timerange,
        suffix="oos",
        pair=primary_symbol,
        config_path=config_path,
        userdir=userdir,
        timeout_seconds=timeout_seconds,
        cost_model=resolved_cost_model,
    )
    walk_forward = [
        _run_window(
            manifest,
            timerange=timerange,
            suffix=f"wf_{index}",
            pair=primary_symbol,
            config_path=config_path,
            userdir=userdir,
            timeout_seconds=timeout_seconds,
            cost_model=resolved_cost_model,
        )
        for index, timerange in enumerate(walk_forward_ranges, start=1)
    ]
    fee_slippage = _run_window(
        manifest,
        timerange=source_backtest.timerange,
        suffix="fee_slippage",
        pair=primary_symbol,
        config_path=config_path,
        userdir=userdir,
        timeout_seconds=timeout_seconds,
        cost_model=resolved_cost_model,
    )
    cross_symbol = run_cross_symbol_validation(
        manifest=manifest,
        source_backtest=source_backtest,
        primary_symbol=primary_symbol,
        related_symbols=related_symbols,
        stress_symbols=stress_symbols,
        config_path=config_path,
        userdir=userdir,
        timeout_seconds=timeout_seconds,
        cost_model=resolved_cost_model,
    )

    if out_of_sample.status != BacktestStatus.PASSED:
        findings.append("Real out-of-sample backtest failed.")
    if any(report.status != BacktestStatus.PASSED for report in walk_forward):
        findings.append("One or more real walk-forward windows failed.")
    if fee_slippage.status != BacktestStatus.PASSED:
        findings.append("Fee/slippage scenario failed under current Freqtrade configuration.")
    if not cross_symbol.passed:
        findings.append("Cross-symbol validation did not meet pass-rate criteria.")

    passed = not findings
    suite = RealBacktestValidationSuiteReport(
        report_id=f"real_validation_{source_backtest.backtest_id}",
        strategy_id=manifest.strategy_id,
        source_backtest_id=source_backtest.backtest_id,
        out_of_sample_backtest_id=out_of_sample.backtest_id,
        walk_forward_backtest_ids=[report.backtest_id for report in walk_forward],
        fee_slippage_backtest_id=fee_slippage.backtest_id,
        cross_symbol_report_id=cross_symbol.report_id,
        executed=True,
        passed=passed,
        findings=findings or ["Real validation suite passed."],
    )
    return suite, out_of_sample, walk_forward, fee_slippage, cross_symbol


def run_cross_symbol_validation(
    manifest: StrategyManifest,
    source_backtest: BacktestReport,
    primary_symbol: str,
    related_symbols: list[str],
    stress_symbols: list[str],
    config_path: Path,
    userdir: Path,
    timeout_seconds: int,
    cost_model: BacktestCostModel | None = None,
) -> CrossSymbolValidationReport:
    resolved_cost_model = cost_model or default_backtest_cost_model_from_env()
    symbols = list(dict.fromkeys([primary_symbol, *related_symbols, *stress_symbols]))
    results = []
    for symbol in symbols:
        report = _run_window(
            manifest,
            timerange=source_backtest.timerange,
            suffix=f"symbol_{_safe_symbol(symbol)}",
            pair=symbol,
            config_path=config_path,
            userdir=userdir,
            timeout_seconds=timeout_seconds,
            cost_model=resolved_cost_model,
        )
        results.append(_symbol_result(symbol, report, primary_symbol, related_symbols))

    passed_count = sum(result.passed for result in results)
    pass_rate = 0 if not results else passed_count / len(results)
    primary_passed = next((item.passed for item in results if item.symbol == primary_symbol), False)
    related = [item for item in results if item.symbol in related_symbols]
    related_pass_rate = 0 if not related else sum(item.passed for item in related) / len(related)
    passed = primary_passed and related_pass_rate >= 0.5
    label = _robustness_label(primary_passed, related_pass_rate, pass_rate)
    findings = [
        f"Cross-symbol pass rate: {pass_rate:.2f}.",
        f"Related-symbol pass rate: {related_pass_rate:.2f}.",
        f"Robustness label: {label}.",
    ]
    return CrossSymbolValidationReport(
        report_id=f"cross_symbol_{source_backtest.backtest_id}",
        strategy_id=manifest.strategy_id,
        source_backtest_id=source_backtest.backtest_id,
        primary_symbol=primary_symbol,
        related_symbols=related_symbols,
        stress_symbols=stress_symbols,
        results=results,
        pass_rate=round(pass_rate, 6),
        robustness_label=label,
        passed=passed,
        findings=findings,
    )


def _run_window(
    manifest: StrategyManifest,
    timerange: str,
    suffix: str,
    pair: str,
    config_path: Path,
    userdir: Path,
    timeout_seconds: int,
    cost_model: BacktestCostModel | None = None,
) -> BacktestReport:
    report, _, _ = run_freqtrade_backtest(
        manifest,
        timerange=timerange,
        config_path=config_path,
        userdir=userdir,
        timeout_seconds=timeout_seconds,
        pairs=[pair],
        backtest_id_suffix=suffix,
        cost_model=cost_model or default_backtest_cost_model_from_env(),
    )
    return report


def _symbol_result(
    symbol: str,
    report: BacktestReport,
    primary_symbol: str,
    related_symbols: list[str],
) -> SymbolValidationResult:
    if symbol == primary_symbol:
        classification = "primary"
    elif symbol in related_symbols:
        classification = "related"
    else:
        classification = "stress"
    return SymbolValidationResult(
        symbol=symbol,
        backtest_id=report.backtest_id,
        total_return=report.total_return,
        profit_factor=report.profit_factor,
        sharpe=report.sharpe,
        max_drawdown=report.max_drawdown,
        trades=report.trades,
        passed=report.status == BacktestStatus.PASSED,
        classification=classification,
    )


def _robustness_label(primary_passed: bool, related_pass_rate: float, pass_rate: float) -> str:
    if not primary_passed:
        return "primary_failed"
    if pass_rate >= 0.7:
        return "cross_symbol_robust"
    if related_pass_rate >= 0.5:
        return "large_cap_or_related_only"
    return "symbol_specific"


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_").lower()


def _symbols_from_env(name: str, defaults: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return defaults
    return [item.strip() for item in raw.split(",") if item.strip()]
