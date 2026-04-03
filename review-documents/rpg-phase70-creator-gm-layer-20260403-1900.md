# Phase 7.0 — Creator / GM Layer Implementation Review

**Date:** 2026-04-03 18:00 UTC
**Phase:** 7.0 — Creator/GM Foundation Pass
**Branch:** copilot/implement-omnix-rpg-design

## Summary

This patch implements the Phase 7.0 creator/GM layer on top of the Phase 6 architecture,
adding structured adventure setup, creator canon state, GM directive state, startup generation
pipeline, recap builder, and GM command processor. All components integrate with the existing
CoherenceCore, GameLoop, and StoryDirector systems.

## New Files

| File | Purpose | Lines |
|------|---------|-------|
| `src/app/rpg/creator/__init__.py` | Module exports | 52 |
| `src/app/rpg/creator/schema.py` | AdventureSetup + 8 seed/constraint dataclasses | 231 |
| `src/app/rpg/creator/canon.py` | CreatorCanonFact + CreatorCanonState | 73 |
| `src/app/rpg/creator/gm_state.py` | GMDirective hierarchy + GMDirectiveState | 149 |
| `src/app/rpg/creator/startup_pipeline.py` | StartupGenerationPipeline (deterministic) | 215 |
| `src/app/rpg/creator/recap.py` | RecapBuilder (canon/session/faction/NPC/thread summaries) | 52 |
| `src/app/rpg/creator/commands.py` | GMCommandProcessor (parse + apply) | 129 |

## Modified Files

| File | Change | Lines Added |
|------|--------|-------------|
| `src/app/rpg/core/game_loop.py` | `_init_creator_systems()`, `start_new_adventure()`, canon/GM/recap methods | +79 |
| `src/app/rpg/narrative/story_director.py` | `set_creator_canon_state()`, `set_gm_directive_state()`, context builders | +20 |
| `src/app/rpg/adventure_setup.py` | `AdventureSetupService` compatibility wrapper | +28 / -1 |

## Test Files

| File | Type | Tests |
|------|------|-------|
| `src/tests/unit/rpg/test_phase70_creator_unit.py` | Unit | 108 |
| `src/tests/functional/test_phase70_creator_functional.py` | Functional | 16 |
| `src/tests/regression/test_phase70_creator_regression.py` | Regression | 14 |
| **Total** | | **138** |

## Architecture Decisions

1. **CoherenceCore as truth owner** — All creator canon facts and GM retcons materialize through CoherenceCore's `insert_fact()` / `upsert_fact()` with `authority="creator_canon"` (highest authority).
2. **Deterministic startup** — StartupGenerationPipeline is schema-driven, no LLM calls. Future phases can add LLM-assisted expansion.
3. **GameLoop as orchestration spine** — `_init_creator_systems()` called during GameLoop.__init__, after coherence core and before recovery manager.
4. **StoryDirector plumbing** — Creator/GM context injected via setter methods and surfaced in `_build_creator_context()` / `_build_gm_context()` which are merged into world_state during `process()`.
5. **RecoveryManager preserved** — Phase 6.5 recovery layer untouched; initialization order is coherence → creator/GM → recovery.

## What This Provides

- Explicit adventure setup schema with validation (required fields, duplicate ID detection)
- Creator canon facts with highest authority level
- GM directive state with 7 directive types (inject_event, pin_thread, retcon, canon_override, pacing, tone, danger)
- Startup materialization into CoherenceCore (facts, threads, scene anchors)
- Creator/GM context available to StoryDirector
- Recap/query support (canon summary, session recap, faction/NPC roster, thread/tension summaries)
- `GameLoop.start_new_adventure(setup_data)` entry point

## What It Does Not Yet Do

- UI wiring
- LLM-assisted startup generation through LLMGateway
- Full GM command language
- Richer directive-to-event emission
- Deeper renderer integration

## Code Diff

```diff
diff --git a/src/app/rpg/adventure_setup.py b/src/app/rpg/adventure_setup.py
index b7e99a3..2cf1ac1 100644
--- a/src/app/rpg/adventure_setup.py
+++ b/src/app/rpg/adventure_setup.py
@@ -1,3 +1,20 @@
+"""Compatibility wrapper for Phase 7 creator-driven adventure setup."""
+
+from __future__ import annotations
+
+from .creator import AdventureSetup, StartupGenerationPipeline
+
+
+class AdventureSetupService:
+    def build_setup(self, payload: dict) -> AdventureSetup:
+        setup = AdventureSetup.from_dict(payload)
+        setup.validate()
+        return setup
+
+    def start_adventure(self, setup: AdventureSetup, game_loop) -> dict:
+        return game_loop.start_new_adventure(setup.to_dict())
+
+
 class AdventureConfig:
     def __init__(self, theme="fantasy", difficulty="medium", player_background="hero"):
         self.theme = theme
@@ -61,4 +78,13 @@ def generate_world(config: AdventureConfig):
     if config.lore_elements:
         world["lore"] = config.lore_elements
 
-    return world
\ No newline at end of file
+    return world
+
+
+__all__ = [
+    "AdventureConfig",
+    "AdventureSetup",
+    "AdventureSetupService",
+    "StartupGenerationPipeline",
+    "generate_world",
+]
\ No newline at end of file
diff --git a/src/app/rpg/core/game_loop.py b/src/app/rpg/core/game_loop.py
index 7d88e33..7a3e1df 100644
--- a/src/app/rpg/core/game_loop.py
+++ b/src/app/rpg/core/game_loop.py
@@ -276,6 +276,9 @@ class GameLoop:
         elif hasattr(self.story_director, "coherence_core"):
             self.story_director.coherence_core = self.coherence_core
 
+        # PHASE 7.0 — CREATOR / GM LAYER
+        self._init_creator_systems()
+
         # PHASE 6.5 — RECOVERY MANAGER
         self._init_recovery_manager()
 
@@ -326,6 +329,13 @@ class GameLoop:
         if hasattr(self, "recovery_manager") and self.recovery_manager is not None:
             self.recovery_manager.set_mode(mode)
 
+        # PHASE 7.0 — propagate creator/GM aware state
+        if hasattr(self, "story_director"):
+            if hasattr(self.story_director, "set_creator_canon_state"):
+                self.story_director.set_creator_canon_state(self.creator_canon_state)
+            if hasattr(self.story_director, "set_gm_directive_state"):
+                self.story_director.set_gm_directive_state(self.gm_directive_state)
+
         # Primary mode propagation happens via system.set_mode() above.
         # The direct determinism mutation below is only a fallback for
         # systems that expose a determinism object but do not fully
@@ -1043,3 +1053,72 @@ class GameLoop:
                 anchor = scene_summary
         if anchor:
             self.recovery_manager.record_last_good_anchor(anchor)
+
+    # -------------------------
+    # PHASE 7.0 — CREATOR / GM
+    # -------------------------
+
+    def _init_creator_systems(self) -> None:
+        from ..creator import (
+            CreatorCanonState,
+            GMDirectiveState,
+            RecapBuilder,
+            StartupGenerationPipeline,
+            GMCommandProcessor,
+        )
+
+        self.creator_canon_state = CreatorCanonState()
+        self.gm_directive_state = GMDirectiveState()
+        self.recap_builder = RecapBuilder()
+        self.gm_command_processor = GMCommandProcessor()
+        self.startup_generation_pipeline = StartupGenerationPipeline(
+            llm_gateway=self.llm_gateway if hasattr(self, "llm_gateway") else None,
+            coherence_core=self.coherence_core,
+            creator_canon_state=self.creator_canon_state,
+        )
+
+        for system_name in ("creator_canon_state", "gm_directive_state"):
+            if system_name not in self._snapshot_systems:
+                self._snapshot_systems.append(system_name)
+
+        if hasattr(self.story_director, "set_creator_canon_state"):
+            self.story_director.set_creator_canon_state(self.creator_canon_state)
+        if hasattr(self.story_director, "set_gm_directive_state"):
+            self.story_director.set_gm_directive_state(self.gm_directive_state)
+
+    def start_new_adventure(self, setup_data: dict) -> dict:
+        from ..creator import AdventureSetup
+
+        setup = AdventureSetup.from_dict(setup_data)
+        setup.validate()
+
+        generated = self.startup_generation_pipeline.generate(setup)
+        self.apply_creator_canon()
+        self.apply_gm_directives()
+        return {
+            "ok": True,
+            "setup": setup.to_dict(),
+            "generated": generated,
+            "canon_summary": self.get_canon_summary(),
+        }
+
+    def apply_creator_canon(self) -> None:
+        self.creator_canon_state.apply_to_coherence(self.coherence_core)
+
+    def apply_gm_directives(self) -> None:
+        self.gm_directive_state.apply_to_coherence(self.coherence_core)
+
+    def build_creator_context(self) -> dict:
+        return {
+            "canon": self.creator_canon_state.serialize_state(),
+            "gm": self.gm_directive_state.build_director_context(),
+        }
+
+    def get_recap(self) -> dict:
+        return self.recap_builder.build_session_recap(self.coherence_core, self.gm_directive_state)
+
+    def get_canon_summary(self) -> dict:
+        return self.recap_builder.build_canon_summary(self.coherence_core, self.creator_canon_state)
+
+    def get_unresolved_threads_summary(self) -> dict:
+        return self.recap_builder.build_unresolved_threads_summary(self.coherence_core)
diff --git a/src/app/rpg/creator/__init__.py b/src/app/rpg/creator/__init__.py
new file mode 100644
index 0000000..7116b42
--- /dev/null
+++ b/src/app/rpg/creator/__init__.py
@@ -0,0 +1,52 @@
+from .schema import (
+    AdventureSetup,
+    LoreConstraint,
+    FactionSeed,
+    LocationSeed,
+    NPCSeed,
+    ThemeConstraint,
+    PacingProfile,
+    SafetyConstraint,
+    ContentBalance,
+)
+from .canon import CreatorCanonFact, CreatorCanonState
+from .gm_state import (
+    GMDirective,
+    InjectEventDirective,
+    PinThreadDirective,
+    RetconDirective,
+    CanonOverrideDirective,
+    PacingDirective,
+    ToneDirective,
+    DangerDirective,
+    GMDirectiveState,
+)
+from .startup_pipeline import StartupGenerationPipeline
+from .recap import RecapBuilder
+from .commands import GMCommandProcessor
+
+__all__ = [
+    "AdventureSetup",
+    "LoreConstraint",
+    "FactionSeed",
+    "LocationSeed",
+    "NPCSeed",
+    "ThemeConstraint",
+    "PacingProfile",
+    "SafetyConstraint",
+    "ContentBalance",
+    "CreatorCanonFact",
+    "CreatorCanonState",
+    "GMDirective",
+    "InjectEventDirective",
+    "PinThreadDirective",
+    "RetconDirective",
+    "CanonOverrideDirective",
+    "PacingDirective",
+    "ToneDirective",
+    "DangerDirective",
+    "GMDirectiveState",
+    "StartupGenerationPipeline",
+    "RecapBuilder",
+    "GMCommandProcessor",
+]
diff --git a/src/app/rpg/creator/canon.py b/src/app/rpg/creator/canon.py
new file mode 100644
index 0000000..b4364dc
--- /dev/null
+++ b/src/app/rpg/creator/canon.py
@@ -0,0 +1,73 @@
+from __future__ import annotations
+
+from dataclasses import asdict, dataclass, field
+from typing import Any
+
+
+@dataclass
+class CreatorCanonFact:
+    fact_id: str
+    subject: str
+    predicate: str
+    value: Any
+    source: str = "creator"
+    authority: str = "creator_canon"
+    metadata: dict[str, Any] = field(default_factory=dict)
+
+    def to_dict(self) -> dict:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "CreatorCanonFact":
+        return cls(**data)
+
+
+class CreatorCanonState:
+    def __init__(self) -> None:
+        self.facts: dict[str, CreatorCanonFact] = {}
+        self.setup_id: str | None = None
+        self.metadata: dict[str, Any] = {}
+
+    def add_fact(self, fact: CreatorCanonFact) -> None:
+        self.facts[fact.fact_id] = fact
+
+    def remove_fact(self, fact_id: str) -> None:
+        self.facts.pop(fact_id, None)
+
+    def get_fact(self, fact_id: str) -> CreatorCanonFact | None:
+        return self.facts.get(fact_id)
+
+    def list_facts(self) -> list[CreatorCanonFact]:
+        return list(self.facts.values())
+
+    def apply_to_coherence(self, coherence_core: Any) -> None:
+        from ..coherence.models import FactRecord
+
+        for fact in self.facts.values():
+            coherence_core.insert_fact(
+                FactRecord(
+                    fact_id=fact.fact_id,
+                    category="world",
+                    subject=fact.subject,
+                    predicate=fact.predicate,
+                    value=fact.value,
+                    authority="creator_canon",
+                    status="confirmed",
+                    metadata=dict(fact.metadata),
+                )
+            )
+
+    def serialize_state(self) -> dict:
+        return {
+            "facts": {k: v.to_dict() for k, v in self.facts.items()},
+            "setup_id": self.setup_id,
+            "metadata": dict(self.metadata),
+        }
+
+    def deserialize_state(self, data: dict) -> None:
+        self.facts = {
+            k: CreatorCanonFact.from_dict(v)
+            for k, v in data.get("facts", {}).items()
+        }
+        self.setup_id = data.get("setup_id")
+        self.metadata = dict(data.get("metadata", {}))
diff --git a/src/app/rpg/creator/commands.py b/src/app/rpg/creator/commands.py
new file mode 100644
index 0000000..22e5916
--- /dev/null
+++ b/src/app/rpg/creator/commands.py
@@ -0,0 +1,129 @@
+from __future__ import annotations
+
+from typing import Any
+
+from .gm_state import (
+    DangerDirective,
+    InjectEventDirective,
+    PinThreadDirective,
+    ToneDirective,
+)
+
+
+class GMCommandProcessor:
+    def parse_command(self, text: str) -> dict:
+        raw = (text or "").strip()
+        lowered = raw.lower()
+
+        if lowered == "restate canon":
+            return {"command": "restate_canon"}
+        if lowered == "what unresolved threads exist?":
+            return {"command": "list_unresolved_threads"}
+        if lowered.startswith("spawn a merchant"):
+            return {"command": "spawn_merchant"}
+        if lowered.startswith("make this city more corrupt"):
+            return {"command": "make_city_more_corrupt"}
+        if lowered.startswith("introduce a hidden faction"):
+            return {"command": "introduce_hidden_faction"}
+        if lowered.startswith("keep this npc alive"):
+            return {"command": "keep_npc_alive"}
+        if lowered.startswith("turn down combat"):
+            return {"command": "turn_down_combat"}
+        if lowered.startswith("switch tone "):
+            return {"command": "switch_tone", "tone": raw[len("switch tone "):].strip() or "darker"}
+
+        return {"command": "unknown", "raw": raw}
+
+    def apply_command(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
+        name = command.get("command")
+        if name == "restate_canon":
+            return self.command_restate_canon(gm_state, coherence_core)
+        if name == "list_unresolved_threads":
+            return self.command_list_unresolved_threads(gm_state, coherence_core)
+        if name == "spawn_merchant":
+            return self.command_spawn_merchant(command, gm_state, coherence_core)
+        if name == "make_city_more_corrupt":
+            return self.command_make_city_more_corrupt(command, gm_state, coherence_core)
+        if name == "introduce_hidden_faction":
+            return self.command_introduce_hidden_faction(command, gm_state, coherence_core)
+        if name == "keep_npc_alive":
+            return self.command_keep_npc_alive(command, gm_state, coherence_core)
+        if name == "turn_down_combat":
+            return self.command_turn_down_combat(command, gm_state, coherence_core)
+        if name == "switch_tone":
+            return self.command_switch_tone(command, gm_state, coherence_core)
+        return {"ok": False, "reason": "unknown_command"}
+
+    def command_restate_canon(self, gm_state: Any, coherence_core: Any) -> dict:
+        return {
+            "ok": True,
+            "canon": coherence_core.get_scene_summary(),
+            "gm": gm_state.build_director_context(),
+        }
+
+    def command_list_unresolved_threads(self, gm_state: Any, coherence_core: Any) -> dict:
+        return {"ok": True, "threads": coherence_core.get_unresolved_threads()}
+
+    def command_spawn_merchant(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
+        directive = InjectEventDirective(
+            directive_id="gm:spawn_merchant",
+            directive_type="inject_event",
+            scope="scene",
+            event_type="npc_spawned",
+            payload={"npc_id": "merchant", "role": "merchant"},
+        )
+        gm_state.add_directive(directive)
+        return {"ok": True, "directive_id": directive.directive_id}
+
+    def command_make_city_more_corrupt(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
+        directive = InjectEventDirective(
+            directive_id="gm:city_corruption",
+            directive_type="inject_event",
+            scope="scene",
+            event_type="world_fact_established",
+            payload={"subject": "city", "predicate": "corruption", "value": "high"},
+        )
+        gm_state.add_directive(directive)
+        return {"ok": True, "directive_id": directive.directive_id}
+
+    def command_introduce_hidden_faction(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
+        directive = InjectEventDirective(
+            directive_id="gm:hidden_faction",
+            directive_type="inject_event",
+            scope="global",
+            event_type="faction_revealed",
+            payload={"faction_id": "hidden_faction"},
+        )
+        gm_state.add_directive(directive)
+        return {"ok": True, "directive_id": directive.directive_id}
+
+    def command_keep_npc_alive(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
+        directive = PinThreadDirective(
+            directive_id="gm:keep_npc_alive",
+            directive_type="pin_thread",
+            scope="global",
+            thread_id="npc_survival",
+            metadata={"survival_required": True},
+        )
+        gm_state.add_directive(directive)
+        return {"ok": True, "directive_id": directive.directive_id}
+
+    def command_turn_down_combat(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
+        directive = DangerDirective(
+            directive_id="gm:danger_low",
+            directive_type="danger",
+            scope="scene",
+            level="low",
+        )
+        gm_state.add_directive(directive)
+        return {"ok": True, "directive_id": directive.directive_id}
+
+    def command_switch_tone(self, command: dict, gm_state: Any, coherence_core: Any) -> dict:
+        directive = ToneDirective(
+            directive_id="gm:tone",
+            directive_type="tone",
+            scope="scene",
+            tone=command.get("tone", "darker"),
+        )
+        gm_state.add_directive(directive)
+        return {"ok": True, "directive_id": directive.directive_id}
diff --git a/src/app/rpg/creator/gm_state.py b/src/app/rpg/creator/gm_state.py
new file mode 100644
index 0000000..9fa9712
--- /dev/null
+++ b/src/app/rpg/creator/gm_state.py
@@ -0,0 +1,149 @@
+from __future__ import annotations
+
+from dataclasses import asdict, dataclass, field
+from typing import Any
+
+
+@dataclass
+class GMDirective:
+    directive_id: str
+    directive_type: str
+    scope: str = "global"
+    enabled: bool = True
+    metadata: dict[str, Any] = field(default_factory=dict)
+
+    def to_dict(self) -> dict:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "GMDirective":
+        return cls(**data)
+
+
+@dataclass
+class InjectEventDirective(GMDirective):
+    event_type: str = ""
+    payload: dict[str, Any] = field(default_factory=dict)
+
+
+@dataclass
+class PinThreadDirective(GMDirective):
+    thread_id: str = ""
+
+
+@dataclass
+class RetconDirective(GMDirective):
+    subject: str = ""
+    predicate: str = ""
+    value: Any = None
+
+
+@dataclass
+class CanonOverrideDirective(GMDirective):
+    fact_id: str = ""
+    value: Any = None
+
+
+@dataclass
+class PacingDirective(GMDirective):
+    style: str = "balanced"
+
+
+@dataclass
+class ToneDirective(GMDirective):
+    tone: str = "neutral"
+
+
+@dataclass
+class DangerDirective(GMDirective):
+    level: str = "medium"
+
+
+DIRECTIVE_TYPES = {
+    "inject_event": InjectEventDirective,
+    "pin_thread": PinThreadDirective,
+    "retcon": RetconDirective,
+    "canon_override": CanonOverrideDirective,
+    "pacing": PacingDirective,
+    "tone": ToneDirective,
+    "danger": DangerDirective,
+}
+
+
+class GMDirectiveState:
+    def __init__(self) -> None:
+        self.directives: dict[str, GMDirective] = {}
+
+    def add_directive(self, directive: GMDirective) -> None:
+        self.directives[directive.directive_id] = directive
+
+    def remove_directive(self, directive_id: str) -> None:
+        self.directives.pop(directive_id, None)
+
+    def clear_scene_scoped_directives(self) -> None:
+        self.directives = {
+            k: v for k, v in self.directives.items() if v.scope != "scene"
+        }
+
+    def list_directives(self) -> list[GMDirective]:
+        return list(self.directives.values())
+
+    def get_active_directives(self) -> list[GMDirective]:
+        return [d for d in self.directives.values() if d.enabled]
+
+    def apply_to_coherence(self, coherence_core: Any) -> None:
+        from ..coherence.models import FactRecord
+
+        for directive in self.get_active_directives():
+            if isinstance(directive, RetconDirective):
+                coherence_core.upsert_fact(
+                    FactRecord(
+                        fact_id=f"gm_retcon:{directive.directive_id}",
+                        category="world",
+                        subject=directive.subject,
+                        predicate=directive.predicate,
+                        value=directive.value,
+                        authority="creator_canon",
+                        status="confirmed",
+                        metadata={"directive_id": directive.directive_id, **directive.metadata},
+                    )
+                )
+            elif isinstance(directive, CanonOverrideDirective):
+                coherence_core.upsert_fact(
+                    FactRecord(
+                        fact_id=directive.fact_id,
+                        category="world",
+                        subject=directive.fact_id.split(":", 1)[0] if ":" in directive.fact_id else directive.fact_id,
+                        predicate="override",
+                        value=directive.value,
+                        authority="creator_canon",
+                        status="confirmed",
+                        metadata={"directive_id": directive.directive_id, **directive.metadata},
+                    )
+                )
+
+    def build_director_context(self) -> dict:
+        active = self.get_active_directives()
+        return {
+            "active_directives": [self._directive_to_dict(d) for d in active],
+            "pacing": [d.style for d in active if isinstance(d, PacingDirective)],
+            "tone": [d.tone for d in active if isinstance(d, ToneDirective)],
+            "danger": [d.level for d in active if isinstance(d, DangerDirective)],
+            "pinned_threads": [d.thread_id for d in active if isinstance(d, PinThreadDirective)],
+        }
+
+    def serialize_state(self) -> dict:
+        return {
+            "directives": {
+                k: self._directive_to_dict(v) for k, v in self.directives.items()
+            }
+        }
+
+    def deserialize_state(self, data: dict) -> None:
+        self.directives = {}
+        for directive_id, payload in data.get("directives", {}).items():
+            cls = DIRECTIVE_TYPES.get(payload.get("directive_type"), GMDirective)
+            self.directives[directive_id] = cls(**payload)
+
+    def _directive_to_dict(self, directive: GMDirective) -> dict:
+        return asdict(directive)
diff --git a/src/app/rpg/creator/recap.py b/src/app/rpg/creator/recap.py
new file mode 100644
index 0000000..a1878c3
--- /dev/null
+++ b/src/app/rpg/creator/recap.py
@@ -0,0 +1,52 @@
+from __future__ import annotations
+
+from typing import Any
+
+
+class RecapBuilder:
+    def build_canon_summary(self, coherence_core: Any, creator_canon_state: Any | None = None) -> dict:
+        canon_facts = []
+        if creator_canon_state is not None:
+            canon_facts = [f.to_dict() for f in creator_canon_state.list_facts()]
+        return {
+            "canon_facts": canon_facts,
+            "scene_summary": coherence_core.get_scene_summary(),
+        }
+
+    def build_session_recap(self, coherence_core: Any, gm_state: Any | None = None) -> dict:
+        return {
+            "scene_summary": coherence_core.get_scene_summary(),
+            "recent_consequences": coherence_core.get_recent_consequences(limit=10),
+            "active_tensions": coherence_core.get_active_tensions(),
+            "unresolved_threads": coherence_core.get_unresolved_threads(),
+            "gm_directives": gm_state.build_director_context() if gm_state else {},
+        }
+
+    def build_active_factions_summary(self, coherence_core: Any) -> dict:
+        factions = []
+        for fact in coherence_core.get_state().stable_world_facts.values():
+            if fact.fact_id.startswith("faction:") and fact.predicate == "exists":
+                factions.append({"faction_id": fact.subject, "metadata": fact.metadata})
+        return {"factions": factions}
+
+    def build_npc_roster(self, coherence_core: Any) -> dict:
+        npcs = []
+        for fact in coherence_core.get_state().stable_world_facts.values():
+            if fact.fact_id.startswith("npc:") and fact.predicate == "name":
+                npcs.append(
+                    {
+                        "npc_id": fact.subject,
+                        "name": fact.value,
+                        "metadata": fact.metadata,
+                    }
+                )
+        return {"npcs": npcs}
+
+    def build_unresolved_threads_summary(self, coherence_core: Any) -> dict:
+        return {"threads": coherence_core.get_unresolved_threads()}
+
+    def build_world_tensions_summary(self, coherence_core: Any) -> dict:
+        return {"active_tensions": coherence_core.get_active_tensions()}
+
+    def build_player_impact_summary(self, coherence_core: Any) -> dict:
+        return {"recent_consequences": coherence_core.get_recent_consequences(limit=10)}
diff --git a/src/app/rpg/creator/schema.py b/src/app/rpg/creator/schema.py
new file mode 100644
index 0000000..28ead64
--- /dev/null
+++ b/src/app/rpg/creator/schema.py
@@ -0,0 +1,231 @@
+from __future__ import annotations
+
+from dataclasses import asdict, dataclass, field
+from typing import Any
+
+
+@dataclass
+class LoreConstraint:
+    name: str
+    description: str
+    authority: str = "creator_canon"
+
+    def to_dict(self) -> dict:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "LoreConstraint":
+        return cls(**data)
+
+
+@dataclass
+class FactionSeed:
+    faction_id: str
+    name: str
+    description: str
+    goals: list[str] = field(default_factory=list)
+    relationships: dict[str, str] = field(default_factory=dict)
+    metadata: dict[str, Any] = field(default_factory=dict)
+
+    def to_dict(self) -> dict:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "FactionSeed":
+        return cls(**data)
+
+
+@dataclass
+class LocationSeed:
+    location_id: str
+    name: str
+    description: str
+    tags: list[str] = field(default_factory=list)
+    metadata: dict[str, Any] = field(default_factory=dict)
+
+    def to_dict(self) -> dict:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "LocationSeed":
+        return cls(**data)
+
+
+@dataclass
+class NPCSeed:
+    npc_id: str
+    name: str
+    role: str
+    description: str
+    goals: list[str] = field(default_factory=list)
+    faction_id: str | None = None
+    location_id: str | None = None
+    must_survive: bool = False
+    metadata: dict[str, Any] = field(default_factory=dict)
+
+    def to_dict(self) -> dict:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "NPCSeed":
+        return cls(**data)
+
+
+@dataclass
+class ThemeConstraint:
+    name: str
+    description: str
+
+    def to_dict(self) -> dict:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "ThemeConstraint":
+        return cls(**data)
+
+
+@dataclass
+class PacingProfile:
+    style: str = "balanced"
+    danger_level: str = "medium"
+    mystery_weight: float = 0.25
+    combat_weight: float = 0.25
+    politics_weight: float = 0.15
+    social_weight: float = 0.35
+
+    def to_dict(self) -> dict:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "PacingProfile":
+        return cls(**data)
+
+
+@dataclass
+class SafetyConstraint:
+    forbidden_themes: list[str] = field(default_factory=list)
+    soft_avoid_themes: list[str] = field(default_factory=list)
+
+    def to_dict(self) -> dict:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "SafetyConstraint":
+        return cls(**data)
+
+
+@dataclass
+class ContentBalance:
+    mystery: float = 0.2
+    combat: float = 0.2
+    politics: float = 0.2
+    exploration: float = 0.2
+    social: float = 0.2
+
+    def to_dict(self) -> dict:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "ContentBalance":
+        return cls(**data)
+
+
+@dataclass
+class AdventureSetup:
+    setup_id: str
+    title: str
+    genre: str
+    setting: str
+    premise: str
+    hard_rules: list[str] = field(default_factory=list)
+    soft_tone_rules: list[str] = field(default_factory=list)
+    lore_constraints: list[LoreConstraint] = field(default_factory=list)
+    factions: list[FactionSeed] = field(default_factory=list)
+    locations: list[LocationSeed] = field(default_factory=list)
+    npc_seeds: list[NPCSeed] = field(default_factory=list)
+    themes: list[ThemeConstraint] = field(default_factory=list)
+    pacing: PacingProfile | None = None
+    safety: SafetyConstraint | None = None
+    content_balance: ContentBalance | None = None
+    forbidden_content: list[str] = field(default_factory=list)
+    canon_notes: list[str] = field(default_factory=list)
+    metadata: dict[str, Any] = field(default_factory=dict)
+
+    def validate(self) -> None:
+        if not self.setup_id:
+            raise ValueError("AdventureSetup.setup_id is required")
+        if not self.title:
+            raise ValueError("AdventureSetup.title is required")
+        if not self.genre:
+            raise ValueError("AdventureSetup.genre is required")
+        if not self.setting:
+            raise ValueError("AdventureSetup.setting is required")
+        if not self.premise:
+            raise ValueError("AdventureSetup.premise is required")
+
+        seen_locations = set()
+        for location in self.locations:
+            if location.location_id in seen_locations:
+                raise ValueError(f"Duplicate location_id: {location.location_id}")
+            seen_locations.add(location.location_id)
+
+        seen_factions = set()
+        for faction in self.factions:
+            if faction.faction_id in seen_factions:
+                raise ValueError(f"Duplicate faction_id: {faction.faction_id}")
+            seen_factions.add(faction.faction_id)
+
+        seen_npcs = set()
+        for npc in self.npc_seeds:
+            if npc.npc_id in seen_npcs:
+                raise ValueError(f"Duplicate npc_id: {npc.npc_id}")
+            seen_npcs.add(npc.npc_id)
+
+    def to_dict(self) -> dict:
+        return {
+            "setup_id": self.setup_id,
+            "title": self.title,
+            "genre": self.genre,
+            "setting": self.setting,
+            "premise": self.premise,
+            "hard_rules": list(self.hard_rules),
+            "soft_tone_rules": list(self.soft_tone_rules),
+            "lore_constraints": [x.to_dict() for x in self.lore_constraints],
+            "factions": [x.to_dict() for x in self.factions],
+            "locations": [x.to_dict() for x in self.locations],
+            "npc_seeds": [x.to_dict() for x in self.npc_seeds],
+            "themes": [x.to_dict() for x in self.themes],
+            "pacing": self.pacing.to_dict() if self.pacing else None,
+            "safety": self.safety.to_dict() if self.safety else None,
+            "content_balance": self.content_balance.to_dict() if self.content_balance else None,
+            "forbidden_content": list(self.forbidden_content),
+            "canon_notes": list(self.canon_notes),
+            "metadata": dict(self.metadata),
+        }
+
+    @classmethod
+    def from_dict(cls, data: dict) -> "AdventureSetup":
+        return cls(
+            setup_id=data["setup_id"],
+            title=data["title"],
+            genre=data["genre"],
+            setting=data["setting"],
+            premise=data["premise"],
+            hard_rules=list(data.get("hard_rules", [])),
+            soft_tone_rules=list(data.get("soft_tone_rules", [])),
+            lore_constraints=[
+                LoreConstraint.from_dict(x) for x in data.get("lore_constraints", [])
+            ],
+            factions=[FactionSeed.from_dict(x) for x in data.get("factions", [])],
+            locations=[LocationSeed.from_dict(x) for x in data.get("locations", [])],
+            npc_seeds=[NPCSeed.from_dict(x) for x in data.get("npc_seeds", [])],
+            themes=[ThemeConstraint.from_dict(x) for x in data.get("themes", [])],
+            pacing=PacingProfile.from_dict(data["pacing"]) if data.get("pacing") else None,
+            safety=SafetyConstraint.from_dict(data["safety"]) if data.get("safety") else None,
+            content_balance=ContentBalance.from_dict(data["content_balance"])
+            if data.get("content_balance")
+            else None,
+            forbidden_content=list(data.get("forbidden_content", [])),
+            canon_notes=list(data.get("canon_notes", [])),
+            metadata=dict(data.get("metadata", {})),
+        )
diff --git a/src/app/rpg/creator/startup_pipeline.py b/src/app/rpg/creator/startup_pipeline.py
new file mode 100644
index 0000000..ab79a8b
--- /dev/null
+++ b/src/app/rpg/creator/startup_pipeline.py
@@ -0,0 +1,215 @@
+from __future__ import annotations
+
+from typing import Any
+
+from .canon import CreatorCanonFact, CreatorCanonState
+from .schema import AdventureSetup
+
+
+class StartupGenerationPipeline:
+    """Deterministic startup materialization pipeline.
+
+    This v1 implementation is schema-driven and deterministic. It does not
+    require live LLM generation. Future phases can add LLM-assisted expansion
+    through the existing LLMGateway, but the state contract remains explicit.
+    """
+
+    def __init__(
+        self,
+        llm_gateway: Any,
+        coherence_core: Any,
+        creator_canon_state: CreatorCanonState | None = None,
+    ) -> None:
+        self.llm_gateway = llm_gateway
+        self.coherence_core = coherence_core
+        self.creator_canon_state = creator_canon_state or CreatorCanonState()
+
+    def generate(self, setup: AdventureSetup) -> dict:
+        setup.validate()
+        world_frame = self.generate_world_frame(setup)
+        opening = self.generate_opening_situation(setup, world_frame)
+        npcs = self.generate_seed_npcs(setup, world_frame)
+        factions = self.generate_seed_factions(setup, world_frame)
+        locations = self.generate_seed_locations(setup, world_frame)
+        threads = self.generate_initial_threads(setup, opening)
+        generated = {
+            "world_frame": world_frame,
+            "opening_situation": opening,
+            "seed_npcs": npcs,
+            "seed_factions": factions,
+            "seed_locations": locations,
+            "initial_threads": threads,
+        }
+        self.materialize_into_coherence(generated)
+        generated["initial_scene_anchor"] = self.create_initial_scene_anchor(generated)
+        return generated
+
+    def generate_world_frame(self, setup: AdventureSetup) -> dict:
+        return {
+            "setup_id": setup.setup_id,
+            "title": setup.title,
+            "genre": setup.genre,
+            "setting": setup.setting,
+            "premise": setup.premise,
+            "hard_rules": list(setup.hard_rules),
+            "soft_tone_rules": list(setup.soft_tone_rules),
+            "canon_notes": list(setup.canon_notes),
+            "forbidden_content": list(setup.forbidden_content),
+        }
+
+    def generate_opening_situation(self, setup: AdventureSetup, world_frame: dict) -> dict:
+        first_location = setup.locations[0].name if setup.locations else setup.setting
+        first_npcs = [npc.name for npc in setup.npc_seeds[:3]]
+        return {
+            "location": first_location,
+            "summary": f"{setup.premise} The story opens in {first_location}.",
+            "present_actors": first_npcs,
+            "active_tensions": list(setup.hard_rules[:2]) or ["The world has expectations the player must navigate."],
+        }
+
+    def generate_seed_npcs(self, setup: AdventureSetup, world_frame: dict) -> list[dict]:
+        return [npc.to_dict() for npc in setup.npc_seeds]
+
+    def generate_seed_factions(self, setup: AdventureSetup, world_frame: dict) -> list[dict]:
+        return [faction.to_dict() for faction in setup.factions]
+
+    def generate_seed_locations(self, setup: AdventureSetup, world_frame: dict) -> list[dict]:
+        return [location.to_dict() for location in setup.locations]
+
+    def generate_initial_threads(self, setup: AdventureSetup, opening_situation: dict) -> list[dict]:
+        return [
+            {
+                "thread_id": f"setup_thread:{setup.setup_id}:opening",
+                "title": setup.premise,
+                "status": "unresolved",
+                "priority": "high",
+                "source": "startup_pipeline",
+                "summary": opening_situation["summary"],
+            }
+        ]
+
+    def materialize_into_coherence(self, generated: dict) -> None:
+        from ..coherence.models import FactRecord, SceneAnchor, ThreadRecord
+
+        world_frame = generated["world_frame"]
+        opening = generated["opening_situation"]
+
+        creator_facts = [
+            CreatorCanonFact(
+                fact_id=f"setup:{world_frame['setup_id']}:genre",
+                subject="world",
+                predicate="genre",
+                value=world_frame["genre"],
+            ),
+            CreatorCanonFact(
+                fact_id=f"setup:{world_frame['setup_id']}:setting",
+                subject="world",
+                predicate="setting",
+                value=world_frame["setting"],
+            ),
+            CreatorCanonFact(
+                fact_id=f"setup:{world_frame['setup_id']}:premise",
+                subject="world",
+                predicate="premise",
+                value=world_frame["premise"],
+            ),
+        ]
+        for fact in creator_facts:
+            self.creator_canon_state.add_fact(fact)
+        self.creator_canon_state.setup_id = world_frame["setup_id"]
+        self.creator_canon_state.apply_to_coherence(self.coherence_core)
+
+        for faction in generated["seed_factions"]:
+            self.coherence_core.insert_fact(
+                FactRecord(
+                    fact_id=f"faction:{faction['faction_id']}:exists",
+                    category="world",
+                    subject=faction["faction_id"],
+                    predicate="exists",
+                    value=True,
+                    authority="creator_canon",
+                    status="confirmed",
+                    metadata={"name": faction["name"]},
+                )
+            )
+
+        for location in generated["seed_locations"]:
+            self.coherence_core.insert_fact(
+                FactRecord(
+                    fact_id=f"location:{location['location_id']}:name",
+                    category="world",
+                    subject=location["location_id"],
+                    predicate="name",
+                    value=location["name"],
+                    authority="creator_canon",
+                    status="confirmed",
+                    metadata={"description": location["description"]},
+                )
+            )
+
+        for npc in generated["seed_npcs"]:
+            self.coherence_core.insert_fact(
+                FactRecord(
+                    fact_id=f"npc:{npc['npc_id']}:name",
+                    category="world",
+                    subject=npc["npc_id"],
+                    predicate="name",
+                    value=npc["name"],
+                    authority="creator_canon",
+                    status="confirmed",
+                    metadata={"role": npc["role"], "must_survive": npc.get("must_survive", False)},
+                )
+            )
+            if npc.get("location_id"):
+                self.coherence_core.insert_fact(
+                    FactRecord(
+                        fact_id=f"{npc['npc_id']}:location",
+                        category="world",
+                        subject=npc["npc_id"],
+                        predicate="location",
+                        value=npc["location_id"],
+                        authority="creator_canon",
+                        status="confirmed",
+                    )
+                )
+
+        for thread in generated["initial_threads"]:
+            self.coherence_core.insert_thread(
+                ThreadRecord(
+                    thread_id=thread["thread_id"],
+                    title=thread["title"],
+                    status="unresolved",
+                    priority=thread.get("priority", "normal"),
+                    notes=[thread.get("summary", "")],
+                    metadata={"source": "startup_pipeline"},
+                )
+            )
+
+        self.coherence_core.push_anchor(
+            SceneAnchor(
+                anchor_id=f"setup_anchor:{world_frame['setup_id']}",
+                tick=0,
+                location=opening.get("location"),
+                present_actors=list(opening.get("present_actors", [])),
+                active_tensions=list(opening.get("active_tensions", [])),
+                unresolved_thread_ids=[t["thread_id"] for t in generated["initial_threads"]],
+                summary=opening.get("summary", ""),
+                scene_fact_ids=["scene:location"],
+                source_event_id="startup_pipeline",
+                metadata={"setup_id": world_frame["setup_id"]},
+            )
+        )
+
+    def create_initial_scene_anchor(self, generated: dict) -> dict:
+        opening = generated["opening_situation"]
+        threads = generated["initial_threads"]
+        return {
+            "anchor_id": f"setup_anchor:{generated['world_frame']['setup_id']}",
+            "tick": 0,
+            "location": opening.get("location"),
+            "present_actors": list(opening.get("present_actors", [])),
+            "active_tensions": list(opening.get("active_tensions", [])),
+            "unresolved_thread_ids": [t["thread_id"] for t in threads],
+            "summary": opening.get("summary", ""),
+            "metadata": {"source": "startup_pipeline"},
+        }
diff --git a/src/app/rpg/narrative/story_director.py b/src/app/rpg/narrative/story_director.py
index ab5e8e3..9cc5a19 100644
--- a/src/app/rpg/narrative/story_director.py
+++ b/src/app/rpg/narrative/story_director.py
@@ -61,6 +61,8 @@ class StoryDirector:
         self.scene_engine = scene_engine or DefaultSceneEngine()
         self.coherence_core = coherence_core
 
+        self.creator_canon_state = None
+        self.gm_directive_state = None
         self._event_log: List[Dict[str, Any]] = []
         self._tick_count = 0
         self.mode: str = "live"
@@ -68,6 +70,12 @@ class StoryDirector:
     def set_coherence_core(self, coherence_core: Any) -> None:
         self.coherence_core = coherence_core
 
+    def set_creator_canon_state(self, creator_canon_state: Any) -> None:
+        self.creator_canon_state = creator_canon_state
+
+    def set_gm_directive_state(self, gm_directive_state: Any) -> None:
+        self.gm_directive_state = gm_directive_state
+
     def set_recovery_manager(self, recovery_manager: Any) -> None:
         """Accept a recovery manager reference (Phase 6.5).
 
@@ -104,6 +112,8 @@ class StoryDirector:
         # 1. Analyze world state from events
         coherence_context = coherence_context or self._build_coherence_context()
         world_state = self._analyze(events, coherence_context=coherence_context)
+        world_state["creator"] = self._build_creator_context()
+        world_state["gm"] = self._build_gm_context()
 
         # 2. Update story arcs
         active_arcs = self.arc_manager.update(world_state)
@@ -174,6 +184,16 @@ class StoryDirector:
             ],
         }
 
+    def _build_creator_context(self) -> Dict[str, Any]:
+        if self.creator_canon_state is None:
+            return {}
+        return self.creator_canon_state.serialize_state()
+
+    def _build_gm_context(self) -> Dict[str, Any]:
+        if self.gm_directive_state is None:
+            return {}
+        return self.gm_directive_state.build_director_context()
+
     def _analyze(self, events: List[Event], coherence_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
         """Analyze events to produce a world state summary.
 
```

## Test Results

All 138 tests pass:
- 108 unit tests (schema, canon, GM state, startup pipeline, recap, commands)
- 16 functional tests (end-to-end flows: startup, GM commands, recap, retcon, multi-entity)
- 14 regression tests (canon authority, idempotency, large setups, serialization roundtrip, StoryDirector integration)

Run command:
```
PYTHONPATH="src" python -m pytest src/tests/unit/rpg/test_phase70_creator_unit.py src/tests/functional/test_phase70_creator_functional.py src/tests/regression/test_phase70_creator_regression.py -v --noconftest
```

