from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.rpg.spatial.serialization import normalize_spatial_graph
from tests.rpg.manual.spatial_fixtures import build_manual_spatial_fixture
from tests.rpg.manual.safe import _safe_dict, _safe_list
from tests.rpg.manual.session_helpers import (
    _ensure_manual_session,
    _ensure_manual_simulation_roots,
    _save_manual_session_for_test,
    _sync_manual_simulation_state,
)


def apply_manual_scenario_setup_by_session_id(
    session_id: str,
    scenario: Dict[str, Any],
    *,
    scenario_name: str = "",
) -> bool:
    session = _ensure_manual_session(session_id)
    if not session:
        raise RuntimeError(f"manual_session_ensure_failed:{session_id}")
    _apply_manual_scenario_setup(
        session,
        scenario,
        scenario_name=scenario_name,
    )
    _save_manual_session_for_test(session_id, session)
    return True


def _apply_manual_scenario_setup(session: Dict[str, Any], scenario: Dict[str, Any], *, scenario_name: str = "") -> bool:
    simulation_state = _ensure_manual_simulation_roots(session)

    setup_spatial_graph = scenario.get("setup_spatial_graph")
    if setup_spatial_graph:
        simulation_state = session.setdefault("simulation_state", {})
        if not isinstance(simulation_state, dict):
            simulation_state = {}
            session["simulation_state"] = simulation_state

        spatial_graph = normalize_spatial_graph(
            build_manual_spatial_fixture(str(setup_spatial_graph))
        )

        if not spatial_graph.get("areas") or not spatial_graph.get("connections"):
            raise RuntimeError(
                "manual_spatial_fixture_empty:"
                + str(scenario.get("name") or "")
                + ":"
                + str(setup_spatial_graph)
            )

        simulation_state["spatial_graph"] = spatial_graph

        # Some manual-runner paths carry a setup payload or metadata object.
        # Keep those in sync if present, but do not require them.
        setup_payload = session.setdefault("setup_payload", {})
        if isinstance(setup_payload, dict):
            metadata = setup_payload.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata_simulation_state = metadata.setdefault("simulation_state", {})
                if isinstance(metadata_simulation_state, dict):
                    metadata_simulation_state["spatial_graph"] = spatial_graph

    runtime_state = _safe_dict(session.get("runtime_state"))
    runtime_settings = _safe_dict(runtime_state.get("runtime_settings"))

    conversation_settings = _safe_dict(scenario.get("conversation_settings"))
    if conversation_settings:
        current = _safe_dict(runtime_settings.get("conversation_settings"))
        current.update(conversation_settings)
        runtime_settings["conversation_settings"] = current

    setup_world_events = _safe_list(scenario.get("setup_world_events"))
    if setup_world_events:
        world_event_state = _safe_dict(simulation_state.get("world_event_state"))
        events = _safe_list(world_event_state.get("events"))
        for index, event in enumerate(setup_world_events, start=1):
            event = _safe_dict(event)
            event.setdefault("event_id", f"manual:world_event:{session_id}:{index}")
            event.setdefault("tick", index)
            events.append(event)
        world_event_state["events"] = events
        simulation_state["world_event_state"] = world_event_state

    setup_journal_entries = _safe_list(scenario.get("setup_journal_entries"))
    if setup_journal_entries:
        journal_state = _safe_dict(simulation_state.get("journal_state"))
        entries = _safe_list(journal_state.get("entries"))
        for index, entry in enumerate(setup_journal_entries, start=1):
            entry = _safe_dict(entry)
            entry.setdefault("entry_id", f"manual:journal:{session_id}:{index}")
            entries.append(entry)
        journal_state["entries"] = entries
        simulation_state["journal_state"] = journal_state

    setup_quest_state = _safe_dict(scenario.get("setup_quest_state"))
    if setup_quest_state:
        simulation_state["quest_state"] = setup_quest_state

    setup_memory_state = _safe_dict(scenario.get("setup_memory_state"))
    if setup_memory_state:
        memory_state = _safe_dict(simulation_state.get("memory_state"))
        memory_state.update(setup_memory_state)
        simulation_state["memory_state"] = memory_state

    setup_conversation_thread_state = _safe_dict(scenario.get("setup_conversation_thread_state"))
    if setup_conversation_thread_state:
        conversation_thread_state = _safe_dict(simulation_state.get("conversation_thread_state"))
        for key, value in setup_conversation_thread_state.items():
            conversation_thread_state[key] = value
        simulation_state["conversation_thread_state"] = conversation_thread_state

    setup_present_npc_state = _safe_dict(scenario.get("setup_present_npc_state"))
    if setup_present_npc_state:
        current = _safe_dict(simulation_state.get("present_npc_state"))
        current.update(setup_present_npc_state)
        simulation_state["present_npc_state"] = current

    setup_npc_reputation_state = _safe_dict(scenario.get("setup_npc_reputation_state"))
    if setup_npc_reputation_state:
        simulation_state["npc_reputation_state"] = deepcopy(setup_npc_reputation_state)

    setup_npc_evolution_state = _safe_dict(scenario.get("setup_npc_evolution_state"))
    if setup_npc_evolution_state:
        simulation_state["npc_evolution_state"] = deepcopy(setup_npc_evolution_state)

    setup_party_state = _safe_dict(scenario.get("setup_party_state"))
    if setup_party_state:
        player_state = _safe_dict(simulation_state.get("player_state"))
        if not player_state:
            player_state = {}
            simulation_state["player_state"] = player_state
        current_party = _safe_dict(player_state.get("party_state"))
        current_party.update(setup_party_state)
        player_state["party_state"] = current_party
        simulation_state["player_state"] = player_state

    setup_interaction_state = _safe_dict(scenario.get("setup_interaction_state"))
    if setup_interaction_state:
        player_state = _safe_dict(simulation_state.get("player_state"))
        if not player_state:
            player_state = {}
        location_id = _safe_str(
            setup_interaction_state.get("player_location_id")
            or player_state.get("location_id")
            or simulation_state.get("location_id")
        )
        if location_id:
            player_state["location_id"] = location_id
            simulation_state["location_id"] = location_id
        simulation_state["scene_objects"] = _safe_list(setup_interaction_state.get("scene_objects"))
        simulation_state["scene_items"] = _safe_list(setup_interaction_state.get("scene_items"))

        scenario_currency = _safe_dict(scenario.get("currency"))
        if scenario_currency:
            player_state["currency"] = {
                "gold": int(scenario_currency.get("gold") or 0),
                "silver": int(scenario_currency.get("silver") or 0),
                "copper": int(scenario_currency.get("copper") or 0),
            }

        if isinstance(setup_interaction_state.get("player_inventory"), dict):
            player_state["inventory"] = _safe_dict(setup_interaction_state.get("player_inventory"))
        if isinstance(setup_interaction_state.get("party_state"), dict):
            player_state["party_state"] = _safe_dict(setup_interaction_state.get("party_state"))
        if "player_hp" in setup_interaction_state:
            player_state["hp"] = int(setup_interaction_state.get("player_hp") or 0)
        if "player_max_hp" in setup_interaction_state:
            player_state["max_hp"] = int(setup_interaction_state.get("player_max_hp") or 1)
        if isinstance(setup_interaction_state.get("merchant_state"), dict):
            simulation_state["merchant_state"] = _safe_dict(
                setup_interaction_state.get("merchant_state")
            )

        if isinstance(setup_interaction_state.get("combat_state"), dict):
            simulation_state["combat_state"] = _safe_dict(
                setup_interaction_state.get("combat_state")
            )
        simulation_state["player_state"] = player_state

        setup_payload = _safe_dict(session.get("setup_payload"))
        metadata = _safe_dict(setup_payload.get("metadata"))
        metadata["simulation_state"] = simulation_state
        setup_payload["metadata"] = metadata
        session["setup_payload"] = setup_payload

        session = _manual_apply_interaction_seed_fields(
            session,
            setup_interaction_state,
        )
        session = _manual_apply_social_seed_fields(
            session,
            setup_interaction_state,
        )

    runtime_state["runtime_settings"] = runtime_settings
    session["runtime_state"] = runtime_state
    _sync_manual_simulation_state(session)


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)