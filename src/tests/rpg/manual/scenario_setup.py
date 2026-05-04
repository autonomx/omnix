from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict

from app.rpg.campaign_director.runtime import apply_campaign_director_tick
from app.rpg.campaign_journal.journal import record_campaign_journal_entry
from app.rpg.companions.offers import accept_companion_offer, refuse_companion_offer
from app.rpg.dialogue_context.rumors import propagate_rumor
from app.rpg.escalation.rules import apply_escalation_rule
from app.rpg.escalation.state import mark_escalation_rule_applied
from app.rpg.lore.transitions import apply_lore_transition
from app.rpg.memory.observation import (
    record_event_observations,
    record_told_memory,
)
from app.rpg.npc_evolution.transitions import apply_npc_evolution_transition
from app.rpg.puzzles.transitions import apply_puzzle_transition
from app.rpg.quest_log.runtime import pin_objective, unpin_objective
from app.rpg.quests.transitions import apply_quest_transition
from app.rpg.social.leverage import add_social_leverage
from app.rpg.social.reputation import (
    set_global_reputation,
    set_relationship_values,
)
from app.rpg.social.resolution import (
    resolve_intimidation,
    resolve_persuasion,
)
from app.rpg.social.state import ensure_social_state, normalize_social_profile
from app.rpg.spatial.serialization import normalize_spatial_graph
from app.rpg.story_arcs.milestones import (
    add_story_arc_milestone,
    complete_story_arc_milestone,
)
from app.rpg.story_arcs.transitions import apply_story_arc_transition
from app.rpg.story_authoring.approval import (
    approve_story_proposal,
    draft_story_proposal_for_approval,
    reject_story_proposal,
)
from app.rpg.story_authoring.runtime import author_story_proposal
from app.rpg.story_event_queue.queue import (
    enqueue_story_event,
    enqueue_story_event_definition,
    process_story_event_queue,
)
from app.rpg.story_events.application import apply_story_event
from app.rpg.story_packs.activation import activate_story_pack, deactivate_story_pack
from app.rpg.story_packs.importer import import_story_pack
from tests.rpg.manual.memory_fixtures import build_manual_memory_event
from tests.rpg.manual.safe import _safe_dict, _safe_list
from tests.rpg.manual.session_helpers import (
    _ensure_manual_session,
    _ensure_manual_simulation_roots,
    _save_manual_session_for_test,
    _sync_manual_simulation_state,
)
from tests.rpg.manual.spatial_fixtures import build_manual_spatial_fixture


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

    simulation_state = session.setdefault("simulation_state", {})

    for memory_event_name in scenario.get("setup_memory_events") or []:
        event = build_manual_memory_event(str(memory_event_name))
        record_event_observations(
            simulation_state,
            event,
            turn_index=int(scenario.get("setup_turn_index") or 1),
        )

    for told in scenario.get("setup_told_memories") or []:
        if not isinstance(told, dict):
            continue
        record_told_memory(
            simulation_state,
            str(told.get("subject_id") or ""),
            speaker_id=str(told.get("speaker_id") or "player"),
            event_id=str(told.get("event_id") or "evt:told"),
            summary=str(told.get("summary") or ""),
            facts=dict(told.get("facts") or {}),
            confidence=float(told.get("confidence") or 0.7),
            turn_index=int(told.get("turn_index") or 1),
            tags=list(told.get("tags") or []),
            verified=bool(told.get("verified")),
        )

    setup_social_state = scenario.get("setup_social_state") or {}
    if isinstance(setup_social_state, dict) and setup_social_state:
        ensure_social_state(simulation_state)
        for npc_id, values in (setup_social_state.get("relationships") or {}).items():
            if isinstance(values, dict):
                simulation_state.setdefault("social_state", {}).setdefault("relationships", {})[str(npc_id)] = values
        for actor_id, value in (setup_social_state.get("global_reputation") or {}).items():
            set_global_reputation(simulation_state, str(actor_id), value)

    setup_social_profiles = scenario.get("setup_social_profiles") or {}
    if isinstance(setup_social_profiles, dict) and setup_social_profiles:
        social_state = ensure_social_state(simulation_state)
        profiles = social_state.setdefault("profiles", {})
        for npc_id, profile in setup_social_profiles.items():
            profiles[str(npc_id)] = normalize_social_profile(
                profile if isinstance(profile, dict) else {},
                npc_id=str(npc_id),
            )

    for leverage in scenario.get("setup_social_leverage") or []:
        if isinstance(leverage, dict):
            add_social_leverage(simulation_state, leverage)

    social_actions = scenario.get("setup_social_actions") or []
    if social_actions:
        social_state = ensure_social_state(simulation_state)
        manual_results = social_state.setdefault("manual_results", {})
        for index, action in enumerate(social_actions, start=1):
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("type") or "")
            result_key = str(action.get("result_key") or f"social_action_{index}")
            if action_type == "persuasion":
                result = resolve_persuasion(
                    simulation_state,
                    str(action.get("npc_id") or ""),
                    actor_id=str(action.get("actor_id") or "player"),
                    request=str(action.get("request") or ""),
                    difficulty=int(action.get("difficulty") or 50),
                    approach=str(action.get("approach") or "polite"),
                    leverage_id=action.get("leverage_id"),
                    current_turn=int(action.get("turn_index") or 1),
                )
                social_state = ensure_social_state(simulation_state)
                manual_results = social_state.setdefault("manual_results", {})
                manual_results[result_key] = result
                manual_results["last_persuasion"] = manual_results[result_key]
            elif action_type == "intimidation":
                result = resolve_intimidation(
                    simulation_state,
                    str(action.get("npc_id") or ""),
                    actor_id=str(action.get("actor_id") or "player"),
                    threat=str(action.get("threat") or ""),
                    severity=int(action.get("severity") or 50),
                    leverage_id=action.get("leverage_id"),
                    witnesses=list(action.get("witnesses") or []),
                    current_turn=int(action.get("turn_index") or 1),
                )
                social_state = ensure_social_state(simulation_state)
                manual_results = social_state.setdefault("manual_results", {})
                manual_results[result_key] = result
                manual_results["last_intimidation"] = manual_results[result_key]

        # Make the normalized social state with manual_results explicit on the
        # authoritative simulation_state before session save/sync.
        simulation_state["social_state"] = social_state

    for transition in scenario.get("setup_lore_transitions") or []:
        if isinstance(transition, dict):
            apply_lore_transition(
                simulation_state,
                transition,
                turn_index=int(
                    transition.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
            )

    for item_id in scenario.get("setup_manual_inventory_items") or []:
        simulation_state.setdefault("manual_inventory_items", [])
        if item_id not in simulation_state["manual_inventory_items"]:
            simulation_state["manual_inventory_items"].append(item_id)

    # Puzzle transitions must run before quest transitions because quests can be
    # gated by puzzle flags, for example:
    #   condition: {"type": "puzzle_flag", ...}
    for transition in scenario.get("setup_puzzle_transitions") or []:
        if isinstance(transition, dict):
            apply_puzzle_transition(
                simulation_state,
                transition,
                turn_index=int(
                    transition.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
            )

    # Quest transitions intentionally run after inventory/puzzle setup so item
    # gates and puzzle gates see the already-authoritative state.
    for transition in scenario.get("setup_quest_transitions") or []:
        if isinstance(transition, dict):
            apply_quest_transition(
                simulation_state,
                transition,
                turn_index=int(
                    transition.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
            )

    for transition in scenario.get("setup_story_arc_transitions") or []:
        if isinstance(transition, dict):
            apply_story_arc_transition(
                simulation_state,
                transition,
                turn_index=int(
                    transition.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
            )

    # Setup story arcs directly (for scenarios that need pre-seeded arc state)
    setup_story_arcs = _safe_list(scenario.get("setup_story_arcs"))
    if setup_story_arcs:
        story_arc_state = _safe_dict(simulation_state.get("story_arc_state"))
        arcs = _safe_dict(story_arc_state.get("arcs"))
        for arc in setup_story_arcs:
            arc = _safe_dict(arc)
            arc_id = str(arc.get("arc_id") or "")
            if arc_id:
                arcs[arc_id] = arc
        story_arc_state["arcs"] = arcs
        simulation_state["story_arc_state"] = story_arc_state

    for event in scenario.get("setup_story_events") or []:
        if isinstance(event, dict):
            apply_story_event(
                simulation_state,
                event,
                turn_index=int(
                    event.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
            )

    for application in scenario.get("setup_escalation_applications") or []:
        if isinstance(application, dict):
            mark_escalation_rule_applied(
                simulation_state,
                rule_id=str(application.get("rule_id") or ""),
                arc_id=str(application.get("arc_id") or ""),
                event_id=str(application.get("event_id") or ""),
                turn_index=int(
                    application.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
            )

    for rule in scenario.get("setup_apply_escalation_rules") or []:
        if isinstance(rule, dict):
            apply_escalation_rule(
                simulation_state,
                rule,
                turn_index=int(
                    rule.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
            )

    for story_pack in scenario.get("setup_story_packs") or []:
        if isinstance(story_pack, dict):
            proposal = story_pack.get("proposal") or story_pack
            starter_quests = story_pack.get("starter_quests")
            import_story_pack(
                simulation_state,
                proposal,
                turn_index=int(
                    story_pack.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
                starter_quests=starter_quests,
            )

    for rumor in scenario.get("setup_rumor_propagations") or []:
        if isinstance(rumor, dict):
            propagate_rumor(
                simulation_state,
                speaker_id=str(rumor.get("speaker_id") or ""),
                lore_id=str(rumor.get("lore_id") or ""),
                summary=str(rumor.get("summary") or ""),
                explicit_hearers=rumor.get("explicit_hearers"),
                turn_index=int(
                    rumor.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
            )

    for transition in scenario.get("setup_npc_evolution_transitions") or []:
        if isinstance(transition, dict):
            apply_npc_evolution_transition(
                simulation_state,
                transition,
                turn_index=int(
                    transition.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
            )

    for offer in scenario.get("setup_companion_offer_actions") or []:
        if isinstance(offer, dict):
            action = str(offer.get("action") or "")
            if action == "accept":
                accept_companion_offer(
                    simulation_state,
                    str(offer.get("npc_id") or ""),
                    arc_id=str(offer.get("arc_id") or ""),
                    turn_index=int(offer.get("turn_index") or scenario.get("setup_turn_index") or 1),
                    min_trust=int(offer.get("min_trust") or 70),
                    max_hostility=int(offer.get("max_hostility") or 40),
                )
            elif action == "refuse":
                refuse_companion_offer(
                    simulation_state,
                    str(offer.get("npc_id") or ""),
                    arc_id=str(offer.get("arc_id") or ""),
                    turn_index=int(offer.get("turn_index") or scenario.get("setup_turn_index") or 1),
                    reason=str(offer.get("reason") or "player_refused"),
                )

    for entry in scenario.get("setup_campaign_journal_entries") or []:
        if isinstance(entry, dict):
            record_campaign_journal_entry(
                simulation_state,
                kind=str(entry.get("kind") or "story"),
                title=str(entry.get("title") or ""),
                summary=str(entry.get("summary") or ""),
                turn_index=int(entry.get("turn_index") or scenario.get("setup_turn_index") or 1),
                visibility=str(entry.get("visibility") or "player"),
                fact_status=str(entry.get("fact_status") or ""),
                arc_ids=entry.get("arc_ids") or [],
                lore_ids=entry.get("lore_ids") or [],
                event_ids=entry.get("event_ids") or [],
                npc_ids=entry.get("npc_ids") or [],
                quest_ids=entry.get("quest_ids") or [],
                tags=entry.get("tags") or [],
                source_id=str(entry.get("source_id") or ""),
                metadata=entry.get("metadata") or {},
            )

    for authoring in scenario.get("setup_story_authoring_runs") or []:
        if isinstance(authoring, dict):
            llm_text_override = authoring.get("llm_text_override")
            if isinstance(llm_text_override, dict):
                llm_text_override = json.dumps(llm_text_override)
            author_story_proposal(
                simulation_state,
                authoring_goal=str(authoring.get("authoring_goal") or "Create a story pack."),
                turn_index=int(authoring.get("turn_index") or scenario.get("setup_turn_index") or 1),
                import_if_valid=bool(authoring.get("import_if_valid", False)),
                repair_once=bool(authoring.get("repair_once", False)),
                llm_text_override=llm_text_override,
            )

    for action in scenario.get("setup_story_authoring_approval_actions") or []:
        if isinstance(action, dict):
            kind = str(action.get("action") or "")
            if kind == "draft":
                llm_text_override = action.get("llm_text_override")
                if isinstance(llm_text_override, dict):
                    llm_text_override = json.dumps(llm_text_override)
                draft_story_proposal_for_approval(
                    simulation_state,
                    authoring_goal=str(action.get("authoring_goal") or "Draft a story pack."),
                    turn_index=int(action.get("turn_index") or scenario.get("setup_turn_index") or 1),
                    llm_text_override=llm_text_override,
                    repair_once=bool(action.get("repair_once", False)),
                )
            elif kind == "approve":
                pending_id = str(action.get("pending_id") or "")
                if not pending_id:
                    pending = simulation_state.get("story_authoring_approval_state", {}).get("pending", [])
                    pending_id = str((pending[-1] if pending else {}).get("pending_id") or "")
                approve_story_proposal(
                    simulation_state,
                    pending_id=pending_id,
                    turn_index=int(action.get("turn_index") or scenario.get("setup_turn_index") or 1),
                    reason=str(action.get("reason") or "gm_approved"),
                )
            elif kind == "reject":
                pending_id = str(action.get("pending_id") or "")
                if not pending_id:
                    pending = simulation_state.get("story_authoring_approval_state", {}).get("pending", [])
                    pending_id = str((pending[-1] if pending else {}).get("pending_id") or "")
                reject_story_proposal(
                    simulation_state,
                    pending_id=pending_id,
                    turn_index=int(action.get("turn_index") or scenario.get("setup_turn_index") or 1),
                    reason=str(action.get("reason") or "gm_rejected"),
                )

    for activation in scenario.get("setup_story_pack_activation_actions") or []:
        if isinstance(activation, dict):
            action = str(activation.get("action") or "")
            pack_id = str(activation.get("pack_id") or "")
            if action == "activate":
                activate_story_pack(
                    simulation_state,
                    pack_id,
                    turn_index=int(activation.get("turn_index") or scenario.get("setup_turn_index") or 1),
                    reason=str(activation.get("reason") or "scenario_activate"),
                )
            elif action == "deactivate":
                deactivate_story_pack(
                    simulation_state,
                    pack_id,
                    turn_index=int(activation.get("turn_index") or scenario.get("setup_turn_index") or 1),
                    reason=str(activation.get("reason") or "scenario_deactivate"),
                )

    for milestone in scenario.get("setup_story_arc_milestones") or []:
        if isinstance(milestone, dict):
            add_story_arc_milestone(
                simulation_state,
                arc_id=str(milestone.get("arc_id") or ""),
                milestone_id=str(milestone.get("milestone_id") or ""),
                title=str(milestone.get("title") or ""),
                summary=str(milestone.get("summary") or ""),
                objective_text=str(milestone.get("objective_text") or ""),
                journal_on_complete=str(milestone.get("journal_on_complete") or ""),
                quest_id=str(milestone.get("quest_id") or ""),
                priority=int(milestone.get("priority") or 50),
                turn_index=int(milestone.get("turn_index") or scenario.get("setup_turn_index") or 1),
                tags=milestone.get("tags") or [],
            )

    for milestone in scenario.get("setup_complete_story_arc_milestones") or []:
        if isinstance(milestone, dict):
            complete_story_arc_milestone(
                simulation_state,
                str(milestone.get("milestone_id") or ""),
                turn_index=int(milestone.get("turn_index") or scenario.get("setup_turn_index") or 1),
                reason=str(milestone.get("reason") or "scenario_setup"),
            )

    for action in scenario.get("setup_quest_log_actions") or []:
        if isinstance(action, dict):
            kind = str(action.get("action") or "")
            objective_id = str(action.get("objective_id") or "")
            if kind == "pin":
                pin_objective(
                    simulation_state,
                    objective_id,
                    turn_index=int(action.get("turn_index") or scenario.get("setup_turn_index") or 1),
                    reason=str(action.get("reason") or "scenario_pin"),
                )
            elif kind == "unpin":
                unpin_objective(
                    simulation_state,
                    objective_id,
                    turn_index=int(action.get("turn_index") or scenario.get("setup_turn_index") or 1),
                    reason=str(action.get("reason") or "scenario_unpin"),
                )

    if isinstance(scenario.get("setup_scene"), dict):
        simulation_state["scene"] = {
            **dict(simulation_state.get("scene") or {}),
            **dict(scenario.get("setup_scene") or {}),
        }

    if isinstance(scenario.get("setup_combat_state"), dict):
        simulation_state["combat_state"] = {
            **dict(simulation_state.get("combat_state") or {}),
            **dict(scenario.get("setup_combat_state") or {}),
        }

    if isinstance(scenario.get("setup_runtime"), dict):
        simulation_state["runtime"] = {
            **dict(simulation_state.get("runtime") or {}),
            **dict(scenario.get("setup_runtime") or {}),
        }

    for item in scenario.get("setup_story_event_queue") or []:
        if isinstance(item, dict):
            if item.get("definition_event_id"):
                enqueue_story_event_definition(
                    simulation_state,
                    str(item.get("definition_event_id") or ""),
                    source=str(item.get("source") or "scenario_setup"),
                    enqueued_turn=int(item.get("enqueued_turn") or scenario.get("setup_turn_index") or 1),
                    due_turn=item.get("due_turn"),
                    delay_turns=int(item.get("delay_turns") or 0),
                    priority=int(item.get("priority") or 50),
                    reason=str(item.get("reason") or ""),
                    metadata=item.get("metadata"),
                )
            else:
                enqueue_story_event(
                    simulation_state,
                    item.get("event") or item,
                    source=str(item.get("source") or "scenario_setup"),
                    enqueued_turn=int(item.get("enqueued_turn") or scenario.get("setup_turn_index") or 1),
                    due_turn=item.get("due_turn"),
                    delay_turns=int(item.get("delay_turns") or 0),
                    priority=int(item.get("priority") or 50),
                    reason=str(item.get("reason") or ""),
                    metadata=item.get("metadata"),
                )

    for tick in scenario.get("setup_story_event_queue_process") or []:
        if isinstance(tick, dict):
            process_story_event_queue(
                simulation_state,
                mode=str(tick.get("mode") or "idle"),
                turn_index=int(tick.get("turn_index") or scenario.get("setup_turn_index") or 1),
                max_applications=int(tick.get("max_applications") or 3),
            )

    for tick in scenario.get("setup_campaign_director_ticks") or []:
        if isinstance(tick, dict):
            apply_campaign_director_tick(
                simulation_state,
                mode=str(tick.get("mode") or "idle"),
                turn_index=int(
                    tick.get("turn_index")
                    or scenario.get("setup_turn_index")
                    or 1
                ),
                arc_id=str(tick.get("arc_id") or ""),
                max_applications=int(tick.get("max_applications") or 1),
            )

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