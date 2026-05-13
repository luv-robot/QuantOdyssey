from app.models import AlternativeDataProvider
from app.services.alternative_data import GlassnodeClient, NansenClient


def test_alternative_data_clients_expose_provider_stubs() -> None:
    glassnode = GlassnodeClient().fetch_metric("active_addresses", symbol="BTC")
    nansen = NansenClient().fetch_metric("smart_money_flow", symbol="ETH")

    assert glassnode.provider == AlternativeDataProvider.GLASSNODE
    assert nansen.provider == AlternativeDataProvider.NANSEN
    assert glassnode.raw["stub"] is True
    assert nansen.raw["stub"] is True
