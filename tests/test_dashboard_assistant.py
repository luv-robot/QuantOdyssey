from datetime import datetime

from app.models import MarketSignal, ResearchTaskType, SignalType, ThesisDataContractStatus
from app.services.assistant import build_dashboard_assistant_answer, build_dashboard_context
from app.services.assistant.deepseek import ChatCompletionResult
from app.storage import QuantRepository


class FakeConfiguredClient:
    provider = "deepseek"
    model = "deepseek-v4-pro"

    def is_configured(self) -> bool:
        return True

    def complete(self, messages, *, temperature=0.2, max_tokens=900):
        assert messages[0]["role"] == "system"
        assert "Dashboard context JSON" in messages[1]["content"]
        return ChatCompletionResult(
            content="这是 DeepSeek 返回的研究助手回答。请看 `Run Detail`。",
            raw={"choices": [{"message": {"content": "ok"}}]},
        )


class FakeMissingClient:
    provider = "deepseek"
    model = "deepseek-v4-pro"

    def is_configured(self) -> bool:
        return False


def test_dashboard_assistant_uses_deepseek_when_configured() -> None:
    repository = QuantRepository()
    context = build_dashboard_context(
        theses=[{"thesis_id": "thesis_1", "title": "Funding fade", "status": "testing"}],
        tasks=[{"task_id": "task_1", "task_type": "baseline_scan", "status": "proposed"}],
    )

    result = build_dashboard_assistant_answer(
        "这个策略为什么被 reject？",
        context=context,
        repository=repository,
        client=FakeConfiguredClient(),
    )

    assert result.used_llm is True
    assert result.provider == "deepseek"
    assert "DeepSeek" in result.answer
    assert repository.get_prompt_log(result.prompt_id) is not None
    response = repository.get_model_response_log(result.response_id)
    assert response is not None
    assert response.parsed_ok is True


def test_dashboard_assistant_falls_back_to_rule_answer_when_key_missing() -> None:
    context = build_dashboard_context(
        catalog_summary={"lean_items": 300, "factor_items": 12},
    )

    result = build_dashboard_assistant_answer(
        "worldquant 因子有什么用？",
        context=context,
        client=FakeMissingClient(),
    )

    assert result.used_llm is False
    assert result.error == "deepseek is not configured."
    assert "WorldQuant-style 因子模板 12 条" in result.answer
    assert "DeepSeek 暂未接通" in result.answer


def test_dashboard_assistant_can_submit_thesis_and_create_harness_tasks(tmp_path) -> None:
    repository = QuantRepository()
    context = build_dashboard_context()
    signal = MarketSignal(
        signal_id="signal_funding_5m",
        created_at=datetime.utcnow(),
        exchange="binance",
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        signal_type=SignalType.FUNDING_OI_EXTREME,
        rank_score=82,
        features={"funding_percentile_30d": 95, "open_interest_percentile_30d": 80},
        hypothesis="Funding and OI crowding may fade.",
        data_sources=["freqtrade:futures_ohlcv:BTC/USDT:USDT:5m", "funding", "historical_open_interest"],
    )

    result = build_dashboard_assistant_answer(
        """
        提交 thesis:
        # Daily RSI Divergence Test
        市场观察
        BTC 日线 RSI 背离可能标记短期衰竭。
        假设
        日线 bullish divergence 之后，价格可能出现 long-only 反弹。
        交易逻辑
        只做多，确认后入场，必须定义 stoploss，超时或反向跌破退出。
        适用市场
        daily mean reversion
        失效条件
        price makes a lower low after confirmation.
        timeframe: 1d
        required_data: daily OHLCV
        long-only
        """,
        context=context,
        repository=repository,
        client=FakeConfiguredClient(),
        available_signals=[signal],
        scratchpad_base_dir=tmp_path,
    )

    assert result.action == "thesis_intake"
    assert result.used_llm is False
    assert result.artifacts is not None
    thesis_id = result.artifacts["thesis_id"]
    signal_id = result.artifacts["signal_id"]
    assert repository.get_research_thesis(thesis_id).title == "Daily RSI Divergence Test"
    saved_contracts = repository.query_thesis_data_contracts(thesis_id=thesis_id)
    assert saved_contracts[0].status == ThesisDataContractStatus.COMPATIBLE
    assert saved_contracts[0].requested_timeframe == "1d"
    assert signal_id.startswith("signal_thesis_seed_")
    tasks = repository.query_research_tasks(thesis_id=thesis_id, limit=10)
    task_types = {task.task_type for task in tasks}
    assert ResearchTaskType.BASELINE_TEST in task_types
    assert ResearchTaskType.REGIME_BUCKET_TEST in task_types
    assert repository.query_research_findings(thesis_id=thesis_id)
    assert repository.query_research_harness_cycles(thesis_id=thesis_id)
    assert "Harness 已生成第一轮研究任务" in result.answer
