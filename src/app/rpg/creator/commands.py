from __future__ import annotations

import re
from typing import Any

from .gm_state import (
    DangerDirective,
    InjectEventDirective,
    PinThreadDirective,
    RevealDirective,
    TargetFactionDirective,
    TargetLocationDirective,
    TargetNPCDirective,
    ToneDirective,
)


class GMCommandProcessor:
    def parse_command(self, text: str) -> dict:
        raw = (text or "").strip()
        lowered = raw.lower()

        # --- structured patterns (Phase 7.1) ---

        m = re.match(r"pin thread\s+(\S+)", lowered)
        if m:
            return {"command": "pin_thread", "thread_id": m.group(1)}

        m = re.match(r"keep npc\s+(\S+)\s+alive", lowered)
        if m:
            return {"command": "keep_npc_alive", "npc_id": m.group(1)}

        m = re.match(r"target npc\s+(\S+)\s+(.*)", lowered)
        if m:
            return {"command": "target_npc", "npc_id": m.group(1), "instruction": m.group(2).strip()}

        m = re.match(r"target faction\s+(\S+)\s+(.*)", lowered)
        if m:
            return {
                "command": "target_faction",
                "faction_id": m.group(1),
                "instruction": m.group(2).strip(),
            }

        m = re.match(r"target location\s+(\S+)\s+(.*)", lowered)
        if m:
            return {
                "command": "target_location",
                "location_id": m.group(1),
                "instruction": m.group(2).strip(),
            }

        m = re.match(r"reveal\s+(\S+)\s+(\S+)(?:\s+timing\s+(\S+))?", lowered)
        if m:
            return {
                "command": "reveal",
                "reveal_type": m.group(1),
                "target_id": m.group(2),
                "timing": m.group(3) or "soon",
            }

        m = re.match(r"set danger\s+(\S+)", lowered)
        if m:
            return {"command": "set_danger", "level": m.group(1)}

        m = re.match(r"set tone\s+(.+)", lowered)
        if m:
            return {"command": "switch_tone", "tone": m.group(1).strip()}

        # --- legacy patterns ---

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
        # Phase 7.1 targeted commands
        if name == "pin_thread":
            return self.command_pin_thread(command, gm_state, coherence_core)
        if name == "target_npc":
            return self.command_target_npc(command, gm_state, coherence_core)
        if name == "target_faction":
            return self.command_target_faction(command, gm_state, coherence_core)
        if name == "target_location":
            return self.command_target_location(command, gm_state, coherence_core)
        if name == "reveal":
            return self.command_reveal(command, gm_state, coherence_core)
        if name == "set_danger":
            return self.command_set_danger(command, gm_state, coherence_core)
        return {"ok": False, "reason": "unknown_command"}

    # ------------------------------------------------------------------
    # Legacy command handlers
    # ------------------------------------------------------------------

    def command_restate_canon(self, gm_state: Any, coherence_core: Any) -> dict:
        return {
            "ok": True,
            "note": "Deterministic GM command shim",
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
        npc_id = command.get("npc_id", "")
        directive = PinThreadDirective(
            directive_id=f"gm:keep_npc_alive:{npc_id}" if npc_id else "gm:keep_npc_alive",
            directive_type="pin_thread",
            scope="global",
            thread_id=command.get("thread_id", "npc_survival"),
            metadata={
                "survival_required": True,
                "npc_id": npc_id,
                "note": "Deterministic placeholder until entity-targeted GM commands are added",
            },
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

    # ------------------------------------------------------------------
    # Phase 7.1 targeted command handlers
    # ------------------------------------------------------------------

    def command_pin_thread(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        thread_id = command.get("thread_id", "")
        directive = PinThreadDirective(
            directive_id=f"gm:pin_thread:{thread_id}",
            directive_type="pin_thread",
            scope="global",
            thread_id=thread_id,
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_target_npc(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        npc_id = command.get("npc_id", "")
        instruction = command.get("instruction", "")
        directive = TargetNPCDirective(
            directive_id=f"gm:target_npc:{npc_id}",
            directive_type="target_npc",
            scope="global",
            npc_id=npc_id,
            instruction=instruction,
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_target_faction(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        faction_id = command.get("faction_id", "")
        instruction = command.get("instruction", "")
        directive = TargetFactionDirective(
            directive_id=f"gm:target_faction:{faction_id}",
            directive_type="target_faction",
            scope="global",
            faction_id=faction_id,
            instruction=instruction,
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_target_location(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        location_id = command.get("location_id", "")
        instruction = command.get("instruction", "")
        directive = TargetLocationDirective(
            directive_id=f"gm:target_location:{location_id}",
            directive_type="target_location",
            scope="global",
            location_id=location_id,
            instruction=instruction,
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_reveal(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        reveal_type = command.get("reveal_type", "")
        target_id = command.get("target_id", "")
        timing = command.get("timing", "soon")
        directive = RevealDirective(
            directive_id=f"gm:reveal:{target_id}",
            directive_type="reveal",
            scope="global",
            reveal_type=reveal_type,
            target_id=target_id,
            timing=timing,
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_set_danger(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        level = command.get("level", "medium")
        directive = DangerDirective(
            directive_id=f"gm:danger_{level}",
            directive_type="danger",
            scope="scene",
            level=level,
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}
