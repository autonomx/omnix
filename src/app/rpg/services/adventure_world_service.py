"""World inspection, simulation, and LLM package helpers for adventure setup."""
from __future__ import annotations

from typing import Any

from ..creator.defaults import apply_adventure_defaults
from ..creator.world_player_actions import apply_player_action
from .adventure_preview_service import (
    _normalize_setup,
    _safe_dict,
    _validate_generated_content,
)

# Phase 2 — World Graph + Simulation Inspector
# ---------------------------------------------------------------------------


def inspect_world(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute a world graph, simulation summary, and entity inspector.

    Read-only and deterministic — does not modify the setup.

    Parameters
    ----------
    payload :
        Raw setup dict (same shape as other creator endpoints).

    Returns
    -------
    dict
        ``{"success": True, "graph": {...}, "simulation": {...}, "inspector": {...}}``
    """
    from ..creator.world_graph import inspect_world as _inspect

    data = dict(payload or {})
    data = apply_adventure_defaults(data)
    return _inspect(data)


# ---------------------------------------------------------------------------
# Phase 2.5 — World Snapshot + Graph Diff
# ---------------------------------------------------------------------------


def inspect_world_snapshot(
    payload: dict[str, Any],
    label: str | None = None,
) -> dict[str, Any]:
    """Build a full snapshot wrapper around the world inspection result.

    Read-only and deterministic — does not modify the setup.
    """
    from ..creator.world_snapshot import build_world_snapshot

    data = dict(payload or {})
    data = apply_adventure_defaults(data)
    snapshot = build_world_snapshot(data, label=label)
    return {"success": True, "snapshot": snapshot}


def compare_world(
    payload_before: dict[str, Any],
    payload_after: dict[str, Any],
) -> dict[str, Any]:
    """Compare two setup payloads and return a graph diff.

    Read-only and deterministic.
    """
    from ..creator.world_snapshot import build_world_snapshot, compute_graph_diff

    before = dict(payload_before or {})
    before = apply_adventure_defaults(before)
    after = dict(payload_after or {})
    after = apply_adventure_defaults(after)

    before_snap = build_world_snapshot(before, label="Before")
    after_snap = build_world_snapshot(after, label="After")

    diff = compute_graph_diff(before_snap["graph"], after_snap["graph"])

    return {
        "success": True,
        "before_snapshot_id": before_snap["snapshot_id"],
        "after_snapshot_id": after_snap["snapshot_id"],
        "diff": diff,
    }


def compare_world_entity(
    payload_before: dict[str, Any],
    payload_after: dict[str, Any],
    entity_id: str,
) -> dict[str, Any]:
    """Compare a specific entity between two setup payloads.

    Read-only and deterministic.
    """
    from ..creator.world_snapshot import (
        build_world_snapshot,
        compute_entity_history_diff,
    )

    before = dict(payload_before or {})
    before = apply_adventure_defaults(before)
    after = dict(payload_after or {})
    after = apply_adventure_defaults(after)

    before_snap = build_world_snapshot(before, label="Before")
    after_snap = build_world_snapshot(after, label="After")

    result = compute_entity_history_diff(
        before_snap["inspector"],
        after_snap["inspector"],
        entity_id,
    )

    return {"success": True, **result}


# ---------------------------------------------------------------------------
# Phase 3A — World Simulation Engine
# ---------------------------------------------------------------------------


def advance_world_simulation(payload: dict[str, Any]) -> dict[str, Any]:
    """Advance the world simulation by one tick.

    Deterministic and non-destructive — returns a copy of the setup
    with the simulation state updated in ``metadata.simulation_state``.

    Returns
    -------
    dict
        ``{"success": True, "updated_setup": ..., "simulation_state": ...,
        "simulation_diff": ..., "summary": [...], "graph": ...,
        "simulation": ..., "inspector": ...}``
    """
    from ..creator.world_graph import inspect_world as _inspect
    from ..creator.world_scene_generator import generate_scenes_from_simulation
    from ..creator.world_simulation import (
        step_simulation_state,
    )

    data = dict(payload or {})
    data = apply_adventure_defaults(data)

    step_result = step_simulation_state(data)
    next_setup = step_result["next_setup"]
    after_state = step_result["after_state"]

    summary = step_result["summary"]
    diff = step_result.get("simulation_diff", {})
    events = step_result.get("events", [])
    consequences = step_result.get("consequences", [])
    effect_diff = step_result.get("effect_diff", {})
    incident_diff = step_result.get("incident_diff", {})
    reaction_diff = step_result.get("reaction_diff", {})
    base_diff = step_result.get("base_diff", {})
    effect_applied_diff = step_result.get("effect_applied_diff", {})

    # Re-run world inspection on the updated setup
    inspection = _inspect(next_setup)

    # Phase 4 — Generate playable scenes from incidents
    scenes = generate_scenes_from_simulation(after_state)

    return {
        "success": True,
        "updated_setup": next_setup,
        "simulation_state": after_state,
        "simulation_state_base": step_result.get("after_state_base"),
        "simulation_diff": diff,
        "base_diff": base_diff,
        "effect_applied_diff": effect_applied_diff,
        "summary": summary,
        "events": events,
        "consequences": consequences,
        "effect_diff": effect_diff,
        "incident_diff": incident_diff,
        "reaction_diff": reaction_diff,
        "scenes": scenes,
        "graph": inspection.get("graph"),
        "simulation": inspection.get("simulation"),
        "inspector": inspection.get("inspector"),
    }


def get_simulation_state(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the current simulation state (or initialise it).

    Read-only — does not advance the tick.
    """
    from ..creator.world_simulation import build_initial_simulation_state

    data = dict(payload or {})
    data = apply_adventure_defaults(data)

    meta = data.get("metadata") or {}
    sim_state = meta.get("simulation_state")
    if not sim_state or "tick" not in sim_state:
        sim_state = build_initial_simulation_state(data)

    return {"success": True, "simulation_state": sim_state}


# ---------------------------------------------------------------------------
# Phase 4.5 — Player Action → Simulation Feedback
# ---------------------------------------------------------------------------


def apply_player_action_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply a player action to the simulation state and advance one tick.

    Implements the gameplay loop:

        Scene → Player Action → Simulation Mutation → New World State → New Scenes

    Parameters
    ----------
    payload :
        Expected keys:
        - ``setup`` — the current adventure setup dict
        - ``action`` — dict with ``type`` and ``target_id``

    Returns
    -------
    dict
        ``{"success": True, "updated_setup": ..., "simulation_state": ...,
        "simulation_diff": ..., "summary": [...], "scenes": [...]}``
    """
    from ..creator.world_graph import inspect_world as _inspect
    from ..creator.world_scene_generator import generate_scenes_from_simulation
    from ..creator.world_simulation import (
        step_simulation_state,
    )

    setup = _safe_dict(payload.get("setup"))
    action = _safe_dict(payload.get("action"))

    # Extract current simulation state
    meta = _safe_dict(setup.get("metadata"))
    sim_state = _safe_dict(meta.get("simulation_state"))

    if not sim_state or "tick" not in sim_state:
        # Initialize simulation state if not present
        from ..creator.world_simulation import build_initial_simulation_state
        data = apply_adventure_defaults(dict(setup))
        sim_state = build_initial_simulation_state(data)

    # Apply the player action to mutate the simulation state
    updated_sim_state = apply_player_action(sim_state, action)

    # Write mutated state back into setup
    meta = _safe_dict(setup) if not setup.get("metadata") else _safe_dict(setup.get("metadata"))
    meta["simulation_state"] = updated_sim_state
    setup["metadata"] = meta

    # Re-run simulation step with the mutated state
    step_result = step_simulation_state(setup)
    next_setup = step_result["next_setup"]
    after_state = step_result["after_state"]

    summary = step_result["summary"]
    diff = step_result.get("simulation_diff", {})
    scenes = generate_scenes_from_simulation(after_state)

    # Re-run world inspection on the updated setup
    inspection = _inspect(next_setup)

    return {
        "success": True,
        **step_result,
        "updated_setup": next_setup,
        "simulation_state": after_state,
        "simulation_diff": diff,
        "summary": summary,
        "scenes": scenes,
        "graph": inspection.get("graph"),
        "simulation": inspection.get("simulation"),
        "inspector": inspection.get("inspector"),
    }


# ---------------------------------------------------------------------------
# Phase E — LLM World Generation service functions
# ---------------------------------------------------------------------------


def generate_world_proposal(
    setup: dict, preferences: dict | None = None
) -> dict:
    """Service-level wrapper for world generation.

    Acquires an LLM gateway (if available) and delegates to the generator.
    Validates the result before returning.
    """
    from ..creator.llm_world_generator import generate_world_bootstrap_proposal
    from ..creator.validation import validate_generated_package
    from ..llm_app_gateway import build_app_llm_gateway

    setup = _normalize_setup(setup)
    setup = _validate_generated_content(setup)
    data = apply_adventure_defaults(dict(setup))
    gateway = build_app_llm_gateway()

    result = generate_world_bootstrap_proposal(
        data,
        preferences=preferences,
        llm_gateway=gateway,
    )

    # Validate quality
    quality_issues = validate_generated_package(result, data)
    result["quality_issues"] = quality_issues
    result["success"] = result.get("status") == "ready"

    return result


def regenerate_world_section(
    setup: dict, section: str, preferences: dict | None = None
) -> dict:
    """Regenerate one section of the world package.

    Generates a full proposal, then extracts only the requested section.
    Valid sections: characters, locations, factions, lore_entries, rumors.
    """
    valid_sections = {"characters", "locations", "factions", "lore_entries", "rumors"}
    if section not in valid_sections:
        return {
            "success": False,
            "error": f"Invalid section: {section}. Must be one of {sorted(valid_sections)}",
        }

    full_proposal = generate_world_proposal(setup, preferences=preferences)
    if not full_proposal.get("success"):
        return full_proposal

    return {
        "success": True,
        "section": section,
        "data": full_proposal.get(section, []),
        "provenance": full_proposal.get("provenance", {}),
        "warnings": full_proposal.get("warnings", []),
    }


def regenerate_world_entity(
    setup: dict, entity_type: str, entity_id: str
) -> dict:
    """Regenerate a single entity within the generated package.

    Creates a focused context containing only the target entity and its
    immediate relationships to preserve coherence and context.
    """
    from ..creator.defaults import apply_adventure_defaults
    from ..creator.llm_world_generator import generate_world_bootstrap_proposal
    from ..shared.llm_gateway import build_app_llm_gateway

    data = apply_adventure_defaults(dict(setup))

    section_map = {
        "character": ("characters", "npc_seeds", "npc_id"),
        "npc": ("characters", "npc_seeds", "npc_id"),
        "location": ("locations", "locations", "location_id"),
        "faction": ("factions", "factions", "faction_id"),
    }
    section_info = section_map.get(entity_type)
    if not section_info:
        return {
            "success": False,
            "error": f"Invalid entity_type: {entity_type}",
        }

    proposal_section, setup_section, id_field = section_info
    existing_entities = list(data.get(setup_section, []))
    target = None
    for entity in existing_entities:
        if entity.get(id_field) == entity_id:
            target = dict(entity)
            break

    if not target:
        return {
            "success": False,
            "error": f"Entity not found in setup: {entity_id}",
        }

    focused_setup = dict(data)
    focused_setup["regeneration_target"] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "current_entity": target,
    }

    if entity_type in ("character", "npc"):
        loc_id = target.get("location_id")
        faction_id = target.get("faction_id")
        focused_setup["npc_seeds"] = [target]
        focused_setup["locations"] = [
            loc for loc in data.get("locations", [])
            if not loc_id or loc.get("location_id") == loc_id
        ][:3]
        focused_setup["factions"] = [
            fac for fac in data.get("factions", [])
            if not faction_id or fac.get("faction_id") == faction_id
        ][:3]
    elif entity_type == "location":
        loc_id = target.get("location_id")
        focused_setup["locations"] = [target]
        focused_setup["npc_seeds"] = [
            npc for npc in data.get("npc_seeds", [])
            if npc.get("location_id") == loc_id
        ][:5]
        focused_setup["factions"] = [
            fac for fac in data.get("factions", [])
            if any(npc.get("faction_id") == fac.get("faction_id") for npc in focused_setup["npc_seeds"])
        ][:3]
    elif entity_type == "faction":
        faction_id = target.get("faction_id")
        focused_setup["factions"] = [target]
        focused_setup["npc_seeds"] = [
            npc for npc in data.get("npc_seeds", [])
            if npc.get("faction_id") == faction_id
        ][:5]
        loc_ids = {npc.get("location_id") for npc in focused_setup["npc_seeds"] if npc.get("location_id")}
        focused_setup["locations"] = [
            loc for loc in data.get("locations", [])
            if loc.get("location_id") in loc_ids
        ][:3]

    gateway = build_app_llm_gateway()
    proposal = generate_world_bootstrap_proposal(
        focused_setup,
        preferences={"entity_focus": entity_type},
        llm_gateway=gateway,
    )

    if proposal.get("status") != "ready":
        return {
            "success": False,
            "error": "Entity regeneration failed",
            "warnings": proposal.get("warnings", []),
        }

    items = list(proposal.get(proposal_section, []))
    regenerated = items[0] if items else None
    if not regenerated:
        return {
            "success": False,
            "error": f"No regenerated {entity_type} returned",
        }

    return {
        "success": True,
        "entity_type": entity_type,
        "entity": regenerated,
        "provenance": proposal.get("provenance", {}),
        "warnings": proposal.get("warnings", []),
    }


def apply_generated_package(
    setup: dict, generated: dict, locked_ids: list | None = None
) -> dict:
    """Accept and merge generated package into setup.

    Returns the merged setup dict.
    """
    from ..creator.llm_world_merge import merge_generated_package_into_setup
    from ..creator.validation import validate_generated_package

    data = apply_adventure_defaults(dict(setup))

    # Validate before merging
    quality_issues = validate_generated_package(generated, data)
    blocking = [i for i in quality_issues if i.get("severity") == "error"]
    if blocking:
        return {
            "success": False,
            "error": "Generated package has blocking quality issues",
            "quality_issues": quality_issues,
        }

    merged = merge_generated_package_into_setup(
        data,
        generated,
        keep_existing_seeds=True,
        locked_ids=locked_ids,
    )

    return {
        "success": True,
        "setup": merged,
        "quality_issues": quality_issues,
    }
