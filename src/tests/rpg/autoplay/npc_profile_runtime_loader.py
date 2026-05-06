from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.npc_evolution.profile_store import (
    attach_loaded_profiles_to_runtime_state,
    load_npc_evolution_profiles_for_runtime,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _id_variants(value: Any) -> set[str]:
    raw = _safe_str(value).strip()
    normed = raw.lower()
    variants = {normed} if normed else set()
    if normed.startswith("npc:"):
        variants.add(normed.split("npc:", 1)[1])
    elif normed:
        variants.add(f"npc:{normed}")
    return {item for item in variants if item}


def _known_npcs_from_state(simulation_state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    for source in (
        _safe_dict(simulation_state.get("npcs")),
        _safe_dict(_safe_dict(simulation_state.get("npc_progression_state")).get("npcs")),
        _safe_dict(_safe_dict(simulation_state.get("npc_profile_state")).get("npcs")),
    ):
        if source:
            return {str(key): _safe_dict(value) for key, value in source.items()}
    return {}


def _present_npc_items(simulation_state: Dict[str, Any]) -> List[Any]:
    simulation_state = _safe_dict(simulation_state)
    direct = (
        _safe_list(simulation_state.get("present_npcs"))
        or _safe_list(simulation_state.get("nearby_npcs"))
        or _safe_list(simulation_state.get("visible_npcs"))
    )
    if direct:
        return direct

    scene = _safe_dict(simulation_state.get("scene"))
    scene_items = (
        _safe_list(scene.get("present_npcs"))
        or _safe_list(scene.get("nearby_npcs"))
        or _safe_list(scene.get("visible_npcs"))
    )
    if scene_items:
        return scene_items

    return []


def npc_ids_for_profile_loading(simulation_state: Dict[str, Any]) -> List[str]:
    """Extract canonical NPC IDs from simulation state for profile loading."""
    known_npcs = _known_npcs_from_state(simulation_state)
    present_items = _present_npc_items(simulation_state)

    canonical_ids = set()
    for item in present_items:
        if isinstance(item, str):
            variants = _id_variants(item)
        elif isinstance(item, dict):
            variants = _id_variants(item.get("id") or item.get("name") or item.get("npc_id"))
        else:
            continue

        for variant in variants:
            # Case-insensitive match
            lower_variant = variant.lower()
            for known_id in known_npcs:
                if lower_variant == known_id.lower():
                    canonical_ids.add(known_id)
                    break
            else:
                # If not known, try to canonicalize further
                clean = variant.lower().replace("npc:", "")
                for known_id in known_npcs:
                    if clean == known_id.lower():
                        canonical_ids.add(known_id)
                        break

    return sorted(canonical_ids)


def load_profiles_into_row_runtime(
    *,
    row: Dict[str, Any],
    simulation_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Load NPC profiles into a runtime row for background context."""
    row = _safe_dict(row)
    simulation_state = _safe_dict(simulation_state)

    npc_ids = npc_ids_for_profile_loading(simulation_state)
    load_result = load_npc_evolution_profiles_for_runtime(npc_ids=npc_ids)

    runtime_state = deepcopy(_safe_dict(row.get("runtime_state")))
    attach_loaded_profiles_to_runtime_state(
        runtime_state=runtime_state,
        load_result=load_result,
    )
    row["runtime_state"] = runtime_state
    row["npc_profile_load_result"] = load_result

    return load_result


def summarize_profile_loads(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize profile loading across a transcript."""
    transcript = _safe_list(transcript)

    loaded_npc_ids: set[str] = set()
    turns_with_profiles = 0
    total_loaded_count = 0
    total_missing_count = 0
    errors: List[Dict[str, Any]] = []

    for turn in transcript:
        turn = _safe_dict(turn)
        load_result = _safe_dict(turn.get("npc_profile_load_result"))
        if not load_result:
            continue

        turns_with_profiles += 1
        total_loaded_count += load_result.get("loaded_count", 0)
        total_missing_count += load_result.get("missing_count", 0)

        for npc_id in _safe_dict(load_result.get("loaded", {})):
            loaded_npc_ids.add(_safe_str(npc_id))

        for error in _safe_list(load_result.get("errors", [])):
            errors.append(error)

    return {
        "ok": not errors,
        "turns_with_profiles": turns_with_profiles,
        "loaded_count": total_loaded_count,
        "missing_count": total_missing_count,
        "loaded_npc_ids": sorted(loaded_npc_ids),
        "errors": errors,
    }