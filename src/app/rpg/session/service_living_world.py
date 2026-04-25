from __future__ import annotations

from typing import Any, Dict

from app.rpg.economy.service_stock import apply_service_stock_purchase
from app.rpg.memory.service_memory import append_service_memory
from app.rpg.memory.service_social_effects import apply_service_social_effects
from app.rpg.session.state_normalization import _safe_dict, _safe_str


def apply_service_living_world_effects(
    simulation_state: Dict[str, Any],
    service_result: Dict[str, Any],
    service_application: Dict[str, Any] | None = None,
    *,
    tick: int = 0,
) -> Dict[str, Any]:
    service_result = _safe_dict(service_result)
    service_application = _safe_dict(service_application)
    if not service_result.get("matched"):
        return {
            "memory_entry": {},
            "social_effects": {},
            "stock_update": {},
        }

    stock_update = {}
    if (
        _safe_str(service_result.get("kind")) == "service_purchase"
        and bool(service_application.get("applied"))
    ):
        stock_update = apply_service_stock_purchase(
            simulation_state,
            service_result,
            tick=tick,
        )

    memory_entry = append_service_memory(
        simulation_state,
        service_result,
        service_application,
        tick=tick,
    )
    social_effects = apply_service_social_effects(
        simulation_state,
        service_result,
        service_application,
        tick=tick,
    )

    return {
        "memory_entry": memory_entry,
        "social_effects": social_effects,
        "stock_update": stock_update,
    }
