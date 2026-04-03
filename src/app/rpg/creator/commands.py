from __future__ import annotations

from typing import Any

from .gm_state import (
    DangerDirective,
    InjectEventDirective,
    PinThreadDirective,
    ToneDirective,
)


class GMCommandProcessor:
    def parse_command(self, text: str) -> dict:
        raw = (text or "").strip()
        lowered = raw.lower()

        if lowered == "restate canon":
            return {"command": "restate_canon"}
        if lowered == "what unresolved threads exist?":
            return {"command": "list_unresolved_threads"}
        if lowered.startswith("spawn a merchant"):
            return {"command": "spawn_merchant"}
        if lowered.startswith("make this city more corrupt"):
            return {"command": "make_city_more_corrupt"}
        if lowered.startswith("introduce a hidden faction"):
            return {"command": "introduce_hidden_faction"}
        if lowered.startswith("keep this npc alive"):
            return {"command": "keep_npc_alive"}
        if lowered.startswith("turn down combat"):
            return {"command": "turn_down_combat"}
        if lowered.startswith("switch tone "):
            return {"command": "switch_tone", "tone": raw[len("switch tone "):].strip() or "darker"}

        return {"command": "unknown", "raw": raw}

    def apply_command(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        name = command.get("command")
        if name == "restate_canon":
            return self.command_restate_canon(gm_state, coherence_core)
        if name == "list_unresolved_threads":
            return self.command_list_unresolved_threads(gm_state, coherence_core)
        if name == "spawn_merchant":
            return self.command_spawn_merchant(command, gm_state, coherence_core)
        if name == "make_city_more_corrupt":
            return self.command_make_city_more_corrupt(command, gm_state, coherence_core)
        if name == "introduce_hidden_faction":
            return self.command_introduce_hidden_faction(command, gm_state, coherence_core)
        if name == "keep_npc_alive":
            return self.command_keep_npc_alive(command, gm_state, coherence_core)
        if name == "turn_down_combat":
            return self.command_turn_down_combat(command, gm_state, coherence_core)
        if name == "switch_tone":
            return self.command_switch_tone(command, gm_state, coherence_core)
        return {"ok": False, "reason": "unknown_command"}

    def command_restate_canon(self, gm_state: Any, coherence_core: Any) -> dict:
        return {
            "ok": True,
            "canon": coherence_core.get_scene_summary(),
            "gm": gm_state.build_director_context(),
        }

    def command_list_unresolved_threads(self, gm_state: Any, coherence_core: Any) -> dict:
        return {"ok": True, "threads": coherence_core.get_unresolved_threads()}

    def command_spawn_merchant(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        directive = InjectEventDirective(
            directive_id="gm:spawn_merchant",
            directive_type="inject_event",
            scope="scene",
            event_type="npc_spawned",
            payload={"npc_id": "merchant", "role": "merchant"},
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_make_city_more_corrupt(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        directive = InjectEventDirective(
            directive_id="gm:city_corruption",
            directive_type="inject_event",
            scope="scene",
            event_type="world_fact_established",
            payload={"subject": "city", "predicate": "corruption", "value": "high"},
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_introduce_hidden_faction(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        directive = InjectEventDirective(
            directive_id="gm:hidden_faction",
            directive_type="inject_event",
            scope="global",
            event_type="faction_revealed",
            payload={"faction_id": "hidden_faction"},
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_keep_npc_alive(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        directive = PinThreadDirective(
            directive_id="gm:keep_npc_alive",
            directive_type="pin_thread",
            scope="global",
            thread_id="npc_survival",
            metadata={"survival_required": True},
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_turn_down_combat(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        directive = DangerDirective(
            directive_id="gm:danger_low",
            directive_type="danger",
            scope="scene",
            level="low",
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_switch_tone(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        directive = ToneDirective(
            directive_id="gm:tone",
            directive_type="tone",
            scope="scene",
            tone=command.get("tone", "darker"),
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}
