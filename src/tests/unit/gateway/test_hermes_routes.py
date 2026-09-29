from app.gateway.app_factory import create_gateway_app
from app.runtime.config import RuntimeConfig


def test_gateway_registers_approved_rpg_ledger_route() -> None:
    app = create_gateway_app(runtime_config=RuntimeConfig())

    paths = {route.path for route in app.routes}
    assert "/api/hermes/rpg/approved-flow/ledger" in paths
