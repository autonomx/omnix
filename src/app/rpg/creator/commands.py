from __future__ import annotations

import re
from typing import Any

from .gm_state import (
    DangerDirective,
    InjectEventDirective,
    OptionFramingDirective,
    PinThreadDirective,
    RecapDirective,
    RevealDirective,
    RetconDirective,
    TargetFactionDirective,
    TargetLocationDirective,
    TargetNPCDirective,
    ToneDirective,
)


class GMCommandProcessor:
    # ------------------------------------------------------------------
    # Entity validation helpers
    # ------------------------------------------------------------------
    def _npc_exists(self, coherence_core: Any, npc_id: str) -> bool:
        facts = coherence_core.get_known_facts(npc_id)
        return bool(facts and facts.get("facts"))

    def _faction_exists(self, coherence_core: Any, faction_id: str) -> bool:
        facts = coherence_core.get_known_facts(faction_id)
        return bool(facts and facts.get("facts"))

    def _location_exists(self, coherence_core: Any, location_id: str) -> bool:
        facts = coherence_core.get_known_facts(location_id)
        return bool(facts and facts.get("facts"))

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

        # --- Phase 7.2 gameplay-control patterns ---

        if lowered == "frame options":
            return {"command": "frame_options"}

        if lowered == "force recap":
            return {"command": "force_recap"}

        m = re.match(r"focus on thread\s+(\S+)", lowered)
        if m:
            return {"command": "focus_thread", "thread_id": m.group(1)}

        if lowered == "raise danger":
            return {"command": "raise_danger"}

        if lowered == "lower danger":
            return {"command": "lower_danger"}

        # --- Phase 7.8 arc-control patterns ---

        m = re.match(r"focus arc\s+(\S+)", lowered)
        if m:
            return {"command": "focus_arc", "arc_id": m.group(1)}

        m = re.match(r"hold reveal\s+(\S+)(?:\s+(.+))?", lowered)
        if m:
            return {
                "command": "hold_reveal",
                "reveal_id": m.group(1),
                "reason": (m.group(2) or "").strip(),
            }

        m = re.match(r"release reveal\s+(\S+)", lowered)
        if m:
            return {"command": "release_reveal", "reveal_id": m.group(1)}

        m = re.match(r"set pacing\s+(\S+)\s+(\S+)", lowered)
        if m:
            return {
                "command": "set_pacing",
                "bias_type": m.group(1),
                "level": m.group(2),
            }

        m = re.match(r"bias scene\s+(\S+)", lowered)
        if m:
            return {"command": "bias_scene", "scene_type": m.group(1)}

        m = re.match(r"accelerate arc\s+(\S+)", lowered)
        if m:
            return {"command": "accelerate_arc", "arc_id": m.group(1)}

        m = re.match(r"delay arc\s+(\S+)", lowered)
        if m:
            return {"command": "delay_arc", "arc_id": m.group(1)}

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
        if name == "focus_npc":
            return self.command_focus_npc(command, gm_state, coherence_core)
        if name == "focus_faction":
            return self.command_focus_faction(command, gm_state, coherence_core)
        if name == "focus_location":
            return self.command_focus_location(command, gm_state, coherence_core)
        if name == "pin_thread":
            return self.command_pin_thread(command, gm_state, coherence_core)
        if name == "reveal":
            return self.command_reveal(command, gm_state, coherence_core)
        if name == "retcon":
            return self.command_retcon(command, gm_state, coherence_core)
        if name == "target_npc":
            return self.command_target_npc(command, gm_state, coherence_core)
        if name == "target_faction":
            return self.command_target_faction(command, gm_state, coherence_core)
        if name == "target_location":
            return self.command_target_location(command, gm_state, coherence_core)
        if name == "set_danger":
            return self.command_set_danger(command, gm_state, coherence_core)
        # Phase 7.2 gameplay-control commands
        if name == "frame_options":
            return self.command_frame_options(command, gm_state, coherence_core)
        if name == "force_recap":
            return self.command_force_recap(command, gm_state, coherence_core)
        if name == "focus_thread":
            return self.command_focus_thread(command, gm_state, coherence_core)
        if name == "raise_danger":
            return self.command_raise_danger(command, gm_state, coherence_core)
        if name == "lower_danger":
            return self.command_lower_danger(command, gm_state, coherence_core)
        # Phase 7.8 arc-control commands
        if name == "focus_arc":
            return self.command_focus_arc(command, gm_state, coherence_core)
        if name == "hold_reveal":
            return self.command_hold_reveal(command, gm_state, coherence_core)
        if name == "release_reveal":
            return self.command_release_reveal(command, gm_state, coherence_core)
        if name == "set_pacing":
            return self.command_set_pacing(command, gm_state, coherence_core)
        if name == "bias_scene":
            return self.command_bias_scene(command, gm_state, coherence_core)
        if name == "accelerate_arc":
            return self.command_accelerate_arc(command, gm_state, coherence_core)
        if name == "delay_arc":
            return self.command_delay_arc(command, gm_state, coherence_core)
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
        thread_id = command.get("thread_id")
        if not thread_id:
            return {"ok": False, "reason": "missing_thread_id"}
        directive = PinThreadDirective(
            directive_id=f"gm:pin_thread:{thread_id}",
            directive_type="pin_thread",
            scope="global",
            thread_id=thread_id,
            priority=command.get("priority", "high"),
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_focus_npc(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        from .gm_state import TargetNPCDirective

        npc_id = command.get("npc_id")
        if not npc_id:
            return {"ok": False, "reason": "missing_npc_id"}
        if not self._npc_exists(coherence_core, npc_id):
            return {"ok": False, "reason": "unknown_npc", "npc_id": npc_id}
        directive = TargetNPCDirective(
            directive_id=f"gm:focus_npc:{npc_id}",
            directive_type="target_npc",
            scope="scene",
            npc_id=npc_id,
            instruction=command.get("instruction", "focus"),
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_focus_faction(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        from .gm_state import TargetFactionDirective

        faction_id = command.get("faction_id")
        if not faction_id:
            return {"ok": False, "reason": "missing_faction_id"}
        if not self._faction_exists(coherence_core, faction_id):
            return {"ok": False, "reason": "unknown_faction", "faction_id": faction_id}
        directive = TargetFactionDirective(
            directive_id=f"gm:focus_faction:{faction_id}",
            directive_type="target_faction",
            scope="scene",
            faction_id=faction_id,
            instruction=command.get("instruction", "focus"),
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_focus_location(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        from .gm_state import TargetLocationDirective

        location_id = command.get("location_id")
        if not location_id:
            return {"ok": False, "reason": "missing_location_id"}
        if not self._location_exists(coherence_core, location_id):
            return {"ok": False, "reason": "unknown_location", "location_id": location_id}
        directive = TargetLocationDirective(
            directive_id=f"gm:focus_location:{location_id}",
            directive_type="target_location",
            scope="scene",
            location_id=location_id,
            instruction=command.get("instruction", "focus"),
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_reveal(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        from .gm_state import RevealDirective

        reveal_type = command.get("reveal_type")
        target_id = command.get("target_id")
        if not reveal_type or not target_id:
            return {"ok": False, "reason": "missing_reveal_fields"}
        directive = RevealDirective(
            directive_id=f"gm:reveal:{reveal_type}:{target_id}",
            directive_type="reveal",
            scope="scene",
            reveal_type=reveal_type,
            target_id=target_id,
            timing=command.get("timing", "soon"),
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_retcon(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        subject = command.get("subject")
        predicate = command.get("predicate")
        value = command.get("value")
        if not subject or not predicate:
            return {"ok": False, "reason": "missing_retcon_fields"}
        directive = RetconDirective(
            directive_id=f"gm:retcon:{subject}:{predicate}",
            directive_type="retcon",
            scope="global",
            subject=subject,
            predicate=predicate,
            value=value,
            reason=command.get("reason", ""),
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

    # ------------------------------------------------------------------
    # Phase 7.2 gameplay-control command handlers
    # ------------------------------------------------------------------

    def command_frame_options(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        directive = OptionFramingDirective(
            directive_id="gm:frame_options",
            directive_type="option_framing",
            scope="scene",
            force=True,
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_force_recap(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        directive = RecapDirective(
            directive_id="gm:force_recap",
            directive_type="recap",
            scope="scene",
            force=True,
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_focus_thread(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        thread_id = command.get("thread_id")
        if not thread_id:
            return {"ok": False, "reason": "missing_thread_id"}
        directive = PinThreadDirective(
            directive_id=f"gm:focus_thread:{thread_id}",
            directive_type="pin_thread",
            scope="scene",
            thread_id=thread_id,
            priority="high",
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_raise_danger(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        directive = DangerDirective(
            directive_id="gm:danger_high",
            directive_type="danger",
            scope="scene",
            level="high",
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_lower_danger(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        directive = DangerDirective(
            directive_id="gm:danger_low",
            directive_type="danger",
            scope="scene",
            level="low",
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    # ------------------------------------------------------------------
    # Phase 7.8 arc-control command handlers
    # ------------------------------------------------------------------

    def command_focus_arc(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        """Focus on a specific narrative arc via a pin-thread directive."""
        arc_id = command.get("arc_id", "")
        if not arc_id:
            return {"ok": False, "reason": "missing_arc_id"}

        # Phase 7.8 tightening — validate arc exists
        threads = coherence_core.query.get_active_threads() if hasattr(coherence_core, "query") else []
        valid_ids = {t.get("thread_id") for t in threads}
        if arc_id not in valid_ids:
            return {"ok": False, "reason": "unknown_arc"}

        directive = PinThreadDirective(
            directive_id=f"gm:focus_arc:{arc_id}",
            directive_type="pin_thread",
            scope="global",
            thread_id=arc_id,
            priority="high",
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_hold_reveal(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        """Hold a scheduled reveal by adding a reveal directive with held timing."""
        reveal_id = command.get("reveal_id", "")
        if not reveal_id:
            return {"ok": False, "reason": "missing_reveal_id"}
        reason = command.get("reason", "held by GM")
        directive = RevealDirective(
            directive_id=f"gm:hold_reveal:{reveal_id}",
            directive_type="reveal",
            scope="global",
            reveal_type="hold",
            target_id=reveal_id,
            timing="held",
            metadata={"hold_reason": reason},
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_release_reveal(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        """Release a held reveal back to scheduled timing."""
        reveal_id = command.get("reveal_id", "")
        if not reveal_id:
            return {"ok": False, "reason": "missing_reveal_id"}
        directive = RevealDirective(
            directive_id=f"gm:release_reveal:{reveal_id}",
            directive_type="reveal",
            scope="global",
            reveal_type="release",
            target_id=reveal_id,
            timing="soon",
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_set_pacing(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        """Set a pacing bias (e.g., 'set pacing danger high')."""
        bias_type = command.get("bias_type", "")
        level = command.get("level", "medium")
        if not bias_type:
            return {"ok": False, "reason": "missing_bias_type"}
        # Map pacing bias types to danger level directives for downstream consumption
        if bias_type == "danger":
            directive = DangerDirective(
                directive_id=f"gm:pacing_danger_{level}",
                directive_type="danger",
                scope="global",
                level=level,
            )
        else:
            # For non-danger pacing biases, create a tone directive as approximation
            directive = ToneDirective(
                directive_id=f"gm:pacing_{bias_type}_{level}",
                directive_type="tone",
                scope="global",
                tone=f"{bias_type}_{level}",
            )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_bias_scene(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        """Bias the next scene toward a specific type."""
        scene_type = command.get("scene_type", "balanced")
        directive = OptionFramingDirective(
            directive_id=f"gm:bias_scene:{scene_type}",
            directive_type="option_framing",
            scope="scene",
            force=True,
            metadata={"scene_type_bias": scene_type},
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_accelerate_arc(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        """Accelerate a narrative arc by pinning its thread with high priority."""
        arc_id = command.get("arc_id", "")
        if not arc_id:
            return {"ok": False, "reason": "missing_arc_id"}
        directive = PinThreadDirective(
            directive_id=f"gm:accelerate_arc:{arc_id}",
            directive_type="pin_thread",
            scope="global",
            thread_id=arc_id,
            priority="high",
            metadata={"accelerated": True},
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}

    def command_delay_arc(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
        """Delay a narrative arc by pinning its thread with low priority."""
        arc_id = command.get("arc_id", "")
        if not arc_id:
            return {"ok": False, "reason": "missing_arc_id"}
        directive = PinThreadDirective(
            directive_id=f"gm:delay_arc:{arc_id}",
            directive_type="pin_thread",
            scope="global",
            thread_id=arc_id,
            priority="low",
            metadata={"delayed": True},
        )
        gm_state.add_directive(directive)
        return {"ok": True, "directive_id": directive.directive_id}
