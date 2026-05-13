from app.flows import run_research_flow
from app.services.researcher import build_researcher_logs
from app.storage import QuantRepository
from tests.test_models import sample_signal


def test_build_researcher_logs_links_prompt_response_strategy_and_signal() -> None:
    signal = sample_signal()
    manifest, code = run_research_flow(signal)

    prompt, response = build_researcher_logs(signal, manifest, code)

    assert prompt.signal_id == signal.signal_id
    assert prompt.strategy_id == manifest.strategy_id
    assert response.prompt_id == prompt.prompt_id
    assert response.parsed_ok is True


def test_research_flow_persists_prompt_and_response_logs() -> None:
    repository = QuantRepository()
    signal = sample_signal()

    manifest, _ = run_research_flow(signal, repository=repository)

    assert repository.get_prompt_log(f"prompt_{manifest.strategy_id}") is not None
    assert repository.get_model_response_log(f"response_{manifest.strategy_id}") is not None
