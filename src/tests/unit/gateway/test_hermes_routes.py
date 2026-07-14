from fastapi import FastAPI

from app.gateway.hermes_routes import register_hermes_routes


def test_gateway_registers_approved_rpg_ledger_route() -> None:
    app = FastAPI()

    register_hermes_routes(app)

    paths = {route.path for route in app.routes}
    assert "/api/hermes/rpg/approved-flow/ledger" in paths
