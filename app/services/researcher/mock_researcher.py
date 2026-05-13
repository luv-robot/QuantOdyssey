from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models import MarketSignal, ModelResponseLog, PromptLog, ResearchThesis, StrategyManifest


def _strategy_name(signal: MarketSignal) -> str:
    prefix = "".join(part.title() for part in signal.signal_type.value.split("_"))
    return f"{prefix}V1"


def build_strategy_code(
    strategy_name: str,
    timeframe: str,
    template_name: str = "volume_momentum",
    refinement_profile: str | None = None,
) -> str:
    if refinement_profile == "diagnosis_refined":
        if template_name == "funding_crowding_fade_short":
            return _build_funding_crowding_fade_short_code(strategy_name, timeframe, refined=True)
        if template_name == "trend_confirmation":
            return _build_refined_trend_confirmation_code(strategy_name, timeframe)
        if template_name == "volatility_breakout":
            return _build_refined_volatility_breakout_code(strategy_name, timeframe)
        return _build_refined_volume_momentum_code(strategy_name, timeframe)
    if template_name == "funding_crowding_fade_short":
        return _build_funding_crowding_fade_short_code(strategy_name, timeframe)
    if template_name == "trend_confirmation":
        return _build_trend_confirmation_code(strategy_name, timeframe)
    if template_name == "volatility_breakout":
        return _build_volatility_breakout_code(strategy_name, timeframe)
    return _build_volume_momentum_code(strategy_name, timeframe)


def _build_funding_crowding_fade_short_code(
    strategy_name: str,
    timeframe: str,
    refined: bool = False,
) -> str:
    stoploss = "-0.045" if refined else "-0.06"
    roi = '{"0": 0.035, "60": 0.018, "240": 0}' if refined else '{"0": 0.04, "90": 0.02, "360": 0}'
    funding_threshold = "92" if refined else "90"
    oi_threshold = "78" if refined else "75"
    return f'''from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class {strategy_name}(IStrategy):
    timeframe = "{timeframe}"
    stoploss = {stoploss}
    minimal_roi = {roi}
    can_short = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["volume_mean"] = dataframe["volume"].rolling(48).mean()
        dataframe["range_high"] = dataframe["high"].rolling(48).max().shift(1)
        dataframe["vwap_proxy"] = (
            (dataframe["close"] * dataframe["volume"]).rolling(288).sum()
            / dataframe["volume"].rolling(288).sum()
        )
        dataframe["price_change_24h"] = dataframe["close"] / dataframe["close"].shift(288) - 1
        dataframe["funding_percentile_30d"] = dataframe.get("funding_percentile_30d", 50)
        dataframe["open_interest_percentile_30d"] = dataframe.get("open_interest_percentile_30d", 50)
        dataframe["recent_high_3"] = dataframe["high"].rolling(3).max()
        dataframe["failed_breakout_3bar"] = (
            (dataframe["recent_high_3"] > dataframe["range_high"])
            & (dataframe["close"] < dataframe["range_high"])
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["funding_percentile_30d"] >= {funding_threshold})
            & (dataframe["open_interest_percentile_30d"] >= {oi_threshold})
            & (dataframe["price_change_24h"] > 0)
            & (dataframe["failed_breakout_3bar"])
            & (dataframe["close"] > dataframe["vwap_proxy"])
            & (dataframe["volume"] > dataframe["volume_mean"] * 1.05),
            "enter_short",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] <= dataframe["vwap_proxy"])
            | (dataframe["funding_percentile_30d"] < 70)
            | (dataframe["close"] > dataframe["recent_high_3"] + dataframe["atr"] * 0.2),
            "exit_short",
        ] = 1
        return dataframe
'''


def _build_volume_momentum_code(strategy_name: str, timeframe: str) -> str:
    return f'''from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class {strategy_name}(IStrategy):
    timeframe = "{timeframe}"
    stoploss = -0.08
    minimal_roi = {{"0": 0.04, "60": 0.02, "180": 0}}
    can_short = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_mean"] = dataframe["volume"].rolling(24).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["volume"] > dataframe["volume_mean"] * 1.2)
            & (dataframe["rsi"] > 48)
            & (dataframe["rsi"] < 78),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["rsi"] < 46) | (dataframe["rsi"] > 82), "exit_long"] = 1
        return dataframe
'''


def _build_refined_volume_momentum_code(strategy_name: str, timeframe: str) -> str:
    return f'''from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class {strategy_name}(IStrategy):
    timeframe = "{timeframe}"
    stoploss = -0.04
    minimal_roi = {{"0": 0.025, "30": 0.012, "120": 0}}
    can_short = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=55)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["volume_mean"] = dataframe["volume"].rolling(36).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["volume"] > dataframe["volume_mean"] * 1.4)
            & (dataframe["rsi"] > 52)
            & (dataframe["rsi"] < 70)
            & (dataframe["close"] > dataframe["ema_fast"])
            & (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["adx"] > 22),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] < 48)
            | (dataframe["close"] < dataframe["ema_fast"])
            | (dataframe["adx"] < 16),
            "exit_long",
        ] = 1
        return dataframe
'''


def _build_trend_confirmation_code(strategy_name: str, timeframe: str) -> str:
    return f'''from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class {strategy_name}(IStrategy):
    timeframe = "{timeframe}"
    stoploss = -0.07
    minimal_roi = {{"0": 0.035, "90": 0.018, "240": 0}}
    can_short = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=55)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["volume_mean"] = dataframe["volume"].rolling(24).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["adx"] > 18)
            & (dataframe["volume"] > dataframe["volume_mean"] * 1.05),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] < dataframe["ema_slow"])
            | (dataframe["adx"] < 12),
            "exit_long",
        ] = 1
        return dataframe
'''


def _build_refined_trend_confirmation_code(strategy_name: str, timeframe: str) -> str:
    return f'''from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class {strategy_name}(IStrategy):
    timeframe = "{timeframe}"
    stoploss = -0.045
    minimal_roi = {{"0": 0.028, "45": 0.012, "180": 0}}
    can_short = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=55)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_mean"] = dataframe["volume"].rolling(36).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["close"] > dataframe["ema_fast"])
            & (dataframe["adx"] > 25)
            & (dataframe["rsi"] > 52)
            & (dataframe["volume"] > dataframe["volume_mean"] * 1.2),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] < dataframe["ema_fast"])
            | (dataframe["adx"] < 18)
            | (dataframe["rsi"] < 48),
            "exit_long",
        ] = 1
        return dataframe
'''


def _build_volatility_breakout_code(strategy_name: str, timeframe: str) -> str:
    return f'''from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class {strategy_name}(IStrategy):
    timeframe = "{timeframe}"
    stoploss = -0.06
    minimal_roi = {{"0": 0.03, "60": 0.015, "180": 0}}
    can_short = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["range_high"] = dataframe["high"].rolling(36).max().shift(1)
        dataframe["volume_mean"] = dataframe["volume"].rolling(36).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["range_high"])
            & (dataframe["volume"] > dataframe["volume_mean"] * 1.1)
            & (dataframe["rsi"] > 50)
            & (dataframe["atr"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] < dataframe["range_high"])
            | (dataframe["rsi"] < 45),
            "exit_long",
        ] = 1
        return dataframe
'''


def _build_refined_volatility_breakout_code(strategy_name: str, timeframe: str) -> str:
    return f'''from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class {strategy_name}(IStrategy):
    timeframe = "{timeframe}"
    stoploss = -0.045
    minimal_roi = {{"0": 0.03, "45": 0.014, "150": 0}}
    can_short = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_mean"] = dataframe["atr"].rolling(36).mean()
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["range_high"] = dataframe["high"].rolling(48).max().shift(1)
        dataframe["volume_mean"] = dataframe["volume"].rolling(48).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["range_high"])
            & (dataframe["close"] > dataframe["ema_fast"])
            & (dataframe["volume"] > dataframe["volume_mean"] * 1.3)
            & (dataframe["rsi"] > 55)
            & (dataframe["rsi"] < 72)
            & (dataframe["atr"] > dataframe["atr_mean"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] < dataframe["ema_fast"])
            | (dataframe["rsi"] < 48),
            "exit_long",
        ] = 1
        return dataframe
'''


def generate_mock_strategy(
    signal: MarketSignal,
    strategy_dir: Path = Path("freqtrade_user_data/strategies"),
    log_dir: Optional[Path] = None,
) -> tuple[StrategyManifest, str]:
    strategy_name = _strategy_name(signal)
    strategy_id = f"strategy_{signal.signal_id}"
    file_path = strategy_dir / f"{strategy_name}.py"
    code = build_strategy_code(strategy_name, signal.timeframe)

    strategy_dir.mkdir(parents=True, exist_ok=True)
    file_path.write_text(code, encoding="utf-8")

    manifest = StrategyManifest(
        strategy_id=strategy_id,
        signal_id=signal.signal_id,
        name=strategy_name,
        file_path=str(file_path),
        generated_at=datetime.utcnow(),
        timeframe=signal.timeframe,
        symbols=[signal.symbol],
        assumptions=[
            "Volume and momentum confirmation can filter low-quality anomaly signals.",
        ],
        failure_modes=[
            "Fake breakouts in choppy or low-liquidity market regimes.",
        ],
    )
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        prompt_log = {
            "agent": "strategy_researcher",
            "prompt_id": "strategy_researcher_v1",
            "signal": signal.model_dump(mode="json"),
            "created_at": datetime.utcnow().isoformat(),
        }
        response_log = {
            "strategy_code": code,
            "manifest": manifest.model_dump(mode="json"),
            "created_at": datetime.utcnow().isoformat(),
        }
        (log_dir / f"{strategy_id}.prompt.json").write_text(
            json.dumps(prompt_log, indent=2),
            encoding="utf-8",
        )
        (log_dir / f"{strategy_id}.response.json").write_text(
            json.dumps(response_log, indent=2),
            encoding="utf-8",
        )
    return manifest, code


def generate_strategy_from_thesis(
    thesis: ResearchThesis,
    signal: MarketSignal,
    strategy_dir: Path = Path("freqtrade_user_data/strategies"),
    log_dir: Optional[Path] = None,
) -> tuple[StrategyManifest, str]:
    base_name = "".join(part for part in thesis.title.title() if part.isalnum())[:32]
    strategy_name = f"{base_name or _strategy_name(signal)}V1"
    if not strategy_name[0].isalpha():
        strategy_name = f"Thesis{strategy_name}"
    strategy_id = f"strategy_{thesis.thesis_id}_{signal.signal_id}"
    file_path = strategy_dir / f"{strategy_name}.py"
    code = build_strategy_code(strategy_name, signal.timeframe)

    strategy_dir.mkdir(parents=True, exist_ok=True)
    file_path.write_text(code, encoding="utf-8")

    manifest = StrategyManifest(
        strategy_id=strategy_id,
        signal_id=signal.signal_id,
        thesis_id=thesis.thesis_id,
        name=strategy_name,
        file_path=str(file_path),
        generated_at=datetime.utcnow(),
        timeframe=signal.timeframe,
        symbols=[signal.symbol],
        assumptions=[
            thesis.hypothesis,
            thesis.trade_logic,
            *thesis.constraints,
        ],
        failure_modes=thesis.invalidation_conditions,
    )
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{strategy_id}.prompt.json").write_text(
            json.dumps(
                {
                    "agent": "human_led_strategy_researcher",
                    "prompt_id": "human_led_strategy_researcher_v1",
                    "thesis": thesis.model_dump(mode="json"),
                    "signal": signal.model_dump(mode="json"),
                    "created_at": datetime.utcnow().isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (log_dir / f"{strategy_id}.response.json").write_text(
            json.dumps(
                {
                    "strategy_code": code,
                    "manifest": manifest.model_dump(mode="json"),
                    "created_at": datetime.utcnow().isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return manifest, code


def build_researcher_logs(
    signal: MarketSignal,
    manifest: StrategyManifest,
    strategy_code: str,
    model: str = "mock-llm",
    prompt_version: str = "strategy_researcher_v1",
    thesis: ResearchThesis | None = None,
) -> tuple[PromptLog, ModelResponseLog]:
    prompt_id = f"prompt_{manifest.strategy_id}"
    prompt = PromptLog(
        prompt_id=prompt_id,
        agent="strategy_researcher",
        model=model,
        signal_id=signal.signal_id,
        strategy_id=manifest.strategy_id,
        prompt_version=prompt_version,
        prompt_text=(
            "Implement a Freqtrade strategy from the human thesis and linked MarketSignal."
            if thesis is not None
            else "Generate a Freqtrade strategy from the structured MarketSignal."
        ),
        input_payload={
            "market_signal": signal.model_dump(mode="json"),
            "research_thesis": None if thesis is None else thesis.model_dump(mode="json"),
        },
    )
    response = ModelResponseLog(
        response_id=f"response_{manifest.strategy_id}",
        prompt_id=prompt_id,
        agent="strategy_researcher",
        model=model,
        output_payload={
            "strategy_code": strategy_code,
            "manifest": manifest.model_dump(mode="json"),
        },
        parsed_ok=True,
    )
    return prompt, response
