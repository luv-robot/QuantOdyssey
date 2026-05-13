from app.services.operations.health import _secret_check


def test_webhook_secret_check_fails_when_missing(monkeypatch):
    monkeypatch.delenv("N8N_WEBHOOK_SECRET", raising=False)

    check = _secret_check()

    assert check.status == "fail"


def test_webhook_secret_check_passes_for_long_secret(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "a" * 32)

    check = _secret_check()

    assert check.status == "ok"
