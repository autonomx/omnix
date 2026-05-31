"""Creator and GM helper methods for GameLoop."""
from __future__ import annotations

from .event_bus import Event


class GameLoopCreatorMixin:
    # -------------------------
    # PHASE 7.0 — CREATOR / GM
    # -------------------------

    def _init_creator_systems(self) -> None:
        from ..creator import (
            CreatorCanonState,
            GMCommandProcessor,
            GMDirectiveState,
            RecapBuilder,
            StartupGenerationPipeline,
        )
        from ..creator.presenters import CreatorStatePresenter

        self.creator_canon_state = CreatorCanonState()
        self.gm_directive_state = GMDirectiveState()
        self.recap_builder = RecapBuilder()
        self.gm_command_processor = GMCommandProcessor()
        self.creator_presenter = CreatorStatePresenter()
        self.startup_generation_pipeline = StartupGenerationPipeline(
            llm_gateway=self.llm_gateway if hasattr(self, "llm_gateway") else None,
            coherence_core=self.coherence_core,
            creator_canon_state=self.creator_canon_state,
        )

        for system_name in ("creator_canon_state", "gm_directive_state"):
            if system_name not in self._snapshot_systems:
                self._snapshot_systems.append(system_name)

        if hasattr(self.story_director, "set_creator_canon_state"):
            self.story_director.set_creator_canon_state(self.creator_canon_state)
        if hasattr(self.story_director, "set_gm_directive_state"):
            self.story_director.set_gm_directive_state(self.gm_directive_state)

    def _emit_pending_gm_events(self) -> None:
        """Emit active GM inject-event directives into the EventBus deterministically.

        This pass is intentionally simple:
        - only inject-event directives are emitted
        - scene-scoped directives are cleared only after successful emission
        - emission happens through the normal EventBus path so downstream
          coherence/director consumers see standard events
        """
        if not hasattr(self, "gm_directive_state") or self.gm_directive_state is None:
            return

        pending = self.gm_directive_state.get_pending_injected_events()
        if not pending:
            return

        emitted_scene_scoped_ids: list[str] = []

        for item in pending:
            directive_id = item.get("directive_id")
            scope = item.get("scope")
            event_type = item.get("event_type")
            payload = dict(item.get("payload", {}) or {})

            if not event_type:
                continue

            self.event_bus.emit(
                Event(
                    event_type,
                    payload,
                    source="gm_directive",
                )
            )

            if scope == "scene" and directive_id:
                emitted_scene_scoped_ids.append(directive_id)

        # Remove only those scene-scoped directives that were actually emitted.
        if emitted_scene_scoped_ids:
            self.gm_directive_state.remove_directives(emitted_scene_scoped_ids)

    def start_new_adventure(self, setup_data: dict) -> dict:
        from ..creator import AdventureSetup

        setup = AdventureSetup.from_dict(setup_data)
        setup.validate()

        generated = self.startup_generation_pipeline.generate(setup)
        # Canon is applied once here after the pipeline has populated creator state.
        self.apply_creator_canon()
        self.apply_gm_directives()
        return {
            "ok": True,
            "setup": setup.to_dict(),
            "generated": generated,
            "canon_summary": self.get_canon_summary(),
        }

    def apply_creator_canon(self) -> None:
        self.creator_canon_state.apply_to_coherence(self.coherence_core)

    def apply_gm_directives(self) -> None:
        self.gm_directive_state.apply_to_coherence(self.coherence_core)

    def build_creator_context(self) -> dict:
        return {
            "canon": self.creator_canon_state.serialize_state(),
            "gm": self.gm_directive_state.build_director_context(),
        }

    def get_recap(self) -> dict:
        return self.recap_builder.build_session_recap(self.coherence_core, self.gm_directive_state)

    def get_canon_summary(self) -> dict:
        return self.recap_builder.build_canon_summary(self.coherence_core, self.creator_canon_state)

    def get_unresolved_threads_summary(self) -> dict:
        return self.recap_builder.build_unresolved_threads_summary(self.coherence_core)

    # ------------------------------------------------------------------
    # Phase 7.1 — validation / preview helpers
    # ------------------------------------------------------------------

    def validate_new_adventure(self, setup_data: dict) -> dict:
        from ..creator.validation import validate_adventure_setup_payload
        result = validate_adventure_setup_payload(setup_data)
        return result.to_dict()

    def prepare_new_adventure(self, setup_data: dict) -> dict:
        from ..creator import AdventureSetup
        from ..creator.defaults import apply_adventure_defaults
        from ..creator.validation import validate_adventure_setup_payload

        data = apply_adventure_defaults(dict(setup_data))
        validation = validate_adventure_setup_payload(data)
        if validation.is_blocking():
            return {
                "ok": False,
                "validation": validation.to_dict(),
            }

        setup = AdventureSetup.from_dict(data).normalize().with_defaults()

        # Resolve starting context so the frontend can show a preview of
        # the opening location and actors without duplicating the logic.
        resolved_context = self.startup_generation_pipeline.resolve_starting_context(setup)

        # Enrich with human-readable names
        location_name = resolved_context.get("location_id") or ""
        for loc in setup.locations:
            if loc.location_id == resolved_context.get("location_id"):
                location_name = loc.name
                break

        npc_names: list[str] = []
        npc_lookup = {npc.npc_id: npc.name for npc in setup.npc_seeds}
        for npc_id in resolved_context.get("npc_ids", []):
            npc_names.append(npc_lookup.get(npc_id, npc_id))

        resolved_context["location_name"] = location_name
        resolved_context["npc_names"] = npc_names

        return {
            "ok": True,
            "validation": validation.to_dict(),
            "preview": self.creator_presenter.present_setup_summary(setup),
            "resolved_context": resolved_context,
        }
