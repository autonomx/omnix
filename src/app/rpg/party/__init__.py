from .party_state import (
    ensure_party_state,
    add_companion,
    remove_companion,
    get_active_companions,
    update_companion_hp,
    update_companion_loyalty,
    update_companion_morale,
    set_companion_status,
    set_companion_equipment,
    clear_companion_equipment,
    build_party_summary,
)

from .companion_ai import (
    run_companion_turns,
    choose_companion_action,
)

from .companion_effects import (
    apply_party_item_to_companion,
)

from .companion_narrative import (
    build_companion_scene_context,
    build_companion_dialogue_context,
    choose_scene_interjections,
    apply_companion_choice_reactions,
    build_companion_presence_summary,
    build_companion_scene_reactions,
    record_companion_narrative_event,
    build_party_narrative_summary,
)

__all__ = [
    "ensure_party_state",
    "add_companion",
    "remove_companion",
    "get_active_companions",
    "update_companion_hp",
    "update_companion_loyalty",
    "update_companion_morale",
    "set_companion_status",
    "set_companion_equipment",
    "clear_companion_equipment",
    "build_party_summary",
    "run_companion_turns",
    "choose_companion_action",
    "apply_party_item_to_companion",
    # Phase 9.3 - Companion Narrative
    "build_companion_scene_context",
    "build_companion_dialogue_context",
    "choose_scene_interjections",
    "apply_companion_choice_reactions",
    "build_companion_presence_summary",
    "build_companion_scene_reactions",
    "record_companion_narrative_event",
    "build_party_narrative_summary",
]
