from __future__ import annotations

from app.rpg.economy_runtime import build_economy_runtime_report


def _state() -> dict[str, object]:
    return {
        "player": {"currency": {"silver": 2}},
        "economy": {
            "merchants": {
                "elara": {
                    "stock": [
                        {"item_id": "ration", "price": {"silver": 1}, "quantity": 3}
                    ]
                }
            },
            "services": [
                {"service_id": "room", "provider_id": "bran", "price": {"silver": 5}}
            ],
        },
    }


def test_phase20_buy_item_smoke() -> None:
    report = build_economy_runtime_report(
        {
            "simulation_state": _state(),
            "economy_action": "buy_item",
            "merchant_id": "elara",
            "item_id": "ration",
        }
    )

    assert report["ready"] is True
    assert report["result"]["stock_after"] == 2


def test_phase20_service_gate_smoke() -> None:
    report = build_economy_runtime_report(
        {"simulation_state": _state(), "economy_action": "service", "service_id": "room"}
    )

    assert report["ready"] is False
    assert report["result"]["reason"] == "insufficient_currency"
