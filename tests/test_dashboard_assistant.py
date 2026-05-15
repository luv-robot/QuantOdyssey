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
