from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


RUMORS: Dict[str, Dict[str, Any]] = {
    "rumor:old_mill_bandits": {
        "rumor_id": "rumor:old_mill_bandits",
        "title": "Bandits near the old mill",
        "summary": "Travelers have seen armed figures near the old mill road.",
        "source_provider_id": "npc:Bran",
        "source_provider_name": "Bran",
        "location_id": "loc_tavern",
        "lead_type": "location",
        "unlocks": {
            "location_hint": "old_mill_road",
        },
        "certainty": "rumor",
        "source": "deterministic_rumor_registry",
    },
    "rumor:market_smugglers": {
        "rumor_id": "rumor:market_smugglers",
        "title": "Smugglers in the market",
        "summary": "Someone has been moving sealed crates through the market after dusk.",
        "source_provider_id": "npc:Elara",
        "source_provider_name": "Elara",
        "location_id": "loc_market",
        "lead_type": "social",
        "unlocks": {
            "npc_hint": "market_porter",
        },
        "certainty": "rumor",
        "source": "deterministic_rumor_registry",
    },
}


def list_rumors() -> List[Dict[str, Any]]:
    return [deepcopy(rumor) for rumor in RUMORS.values()]


def get_rumor(rumor_id: str) -> Dict[str, Any]:
    return deepcopy(_safe_dict(RUMORS.get(_safe_str(rumor_id))))


def select_rumor_for_service(
    service_result: Dict[str, Any],
    simulation_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    service_result = _safe_dict(service_result)
    provider_id = _safe_str(service_result.get("provider_id"))
    provider_name = _safe_str(service_result.get("provider_name"))
    location_id = _safe_str(service_result.get("location_id"))

    candidates: List[Dict[str, Any]] = []
    for rumor in RUMORS.values():
        if provider_id and _safe_str(rumor.get("source_provider_id")) == provider_id:
            candidates.append(deepcopy(rumor))
            continue
        if provider_name and _safe_str(rumor.get("source_provider_name")).lower() == provider_name.lower():
            candidates.append(deepcopy(rumor))
            continue
        if location_id and _safe_str(rumor.get("location_id")) == location_id:
            candidates.append(deepcopy(rumor))

    if not candidates:
        candidates = list_rumors()

    known_ids = set()
    state = _safe_dict(simulation_state)
    journal_state = _safe_dict(state.get("journal_state"))
    for entry in _safe_list(journal_state.get("entries")):
        entry = _safe_dict(entry)
        source_id = _safe_str(entry.get("source_id"))
        if source_id:
            known_ids.add(source_id)

    for candidate in candidates:
        if _safe_str(candidate.get("rumor_id")) not in known_ids:
            return candidate

    return candidates[0] if candidates else {}