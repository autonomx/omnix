"""Scene execution and debug helpers for GameLoop."""
from __future__ import annotations

from ..dialogue.core import DialogueCore
from ..execution.resolver import ActionResolver


class GameLoopExecutionMixin:
    # ------------------------------------------------------------------
    # Phase 7.3 — Scene Execution Layer
    # ------------------------------------------------------------------

    def _init_execution_systems(self) -> None:
        """Initialize the action resolver for scene execution."""
        from ..control.controller import GameplayControlController
        from ..group_dynamics.group_engine import GroupDynamicsEngine
        from ..npc_agency.agency_engine import NPCAgencyEngine
        agency_engine = NPCAgencyEngine(
            group_dynamics_engine=GroupDynamicsEngine(),
        )
        # Phase 8.1 — Dialogue planning layer
        self.dialogue_core = DialogueCore()
        self.action_resolver = ActionResolver(
            npc_agency_engine=agency_engine,
            dialogue_core=self.dialogue_core,
        )
        self.npc_agency_engine = agency_engine
        self.last_dialogue_response: dict | None = None
        # GameplayControlController is already initialized by _init_creator_systems
        # via build_control_output. We create one for direct option lookup.
        if not hasattr(self, "gameplay_control_controller"):
            self.gameplay_control_controller = GameplayControlController()

    def get_last_choice_set(self) -> dict | None:
        """Return the last presented choice set, if any."""
        if hasattr(self, "gameplay_control_controller"):
            return self.gameplay_control_controller.get_last_choice_set()
        return None

    def resolve_selected_option(self, option_id: str) -> dict:
        """Resolve a selected option into events and update coherence + social state.

        This is the main entry point for the scene execution layer.
        It resolves the option, emits events, and applies both coherence
        and social state updates through their respective event/reducer paths.

        Phase 8.2: Also handles encounter start, resolution, and journaling.
        """
        option = self.gameplay_control_controller.select_option(option_id)
        if option is None:
            return {"ok": False, "reason": "unknown_option", "option_id": option_id}

        # Capture scene_summary at resolution time to avoid drift during logging
        scene_summary = (
            self.coherence_core.get_scene_summary() if self.coherence_core else {}
        )

        # Phase 8.2 — explicit-only encounter start
        option_meta = (
            option.get("metadata", {})
            if isinstance(option, dict)
            else getattr(option, "metadata", {})
        ) or {}
        enc_start_mode = None
        if isinstance(option_meta, dict):
            raw_mode = option_meta.get("encounter_start")
            if isinstance(raw_mode, str) and raw_mode.strip():
                enc_start_mode = raw_mode.strip().lower()

        if enc_start_mode and not self.encounter_controller.has_active_encounter():
            participants = self._build_encounter_participants(scene_summary)
            self.encounter_controller.start_encounter(
                mode=enc_start_mode,
                scene_summary=scene_summary,
                participants=participants,
                active_entity_id="player",
                metadata={
                    "started_from_option_id": option.get("option_id")
                    if isinstance(option, dict)
                    else getattr(option, "option_id", None),
                },
                tick=self._tick_count,
            )

        result = self.action_resolver.resolve_choice(
            option=option,
            coherence_core=self.coherence_core,
            gm_state=self.gm_directive_state,
            social_state_core=self.social_state_core,
            arc_control_controller=getattr(self, "arc_control_controller", None),
            campaign_memory_core=getattr(self, "campaign_memory_core", None),
            scene_summary=scene_summary,
            tick=self._tick_count,
        )

        result_dict = result.to_dict()
        self._emit_action_resolution_events(result_dict)

        # Phase 7.6 tightening — ensure identical event ordering for coherence and social state
        raw_events = result_dict.get("events", [])
        if raw_events:
            if self.coherence_core is not None:
                self.coherence_core.apply_events(raw_events)
            if self.social_state_core is not None:
                self.social_state_core.apply_events(raw_events)

        # Phase 8.2 — encounter resolution
        self.last_encounter_resolution = None
        if self.encounter_controller.has_active_encounter():
            resolved_action = result_dict.get("resolved_action", {})
            enc_resolution = self.encounter_resolver.resolve_action(
                encounter_state=self.encounter_controller.get_active_encounter(),
                resolved_action=resolved_action,
                scene_summary=scene_summary,
                coherence_core=self.coherence_core,
                social_state_core=self.social_state_core,
                arc_control_controller=getattr(self, "arc_control_controller", None),
                tick=self._tick_count,
            )
            if enc_resolution is not None:
                self.encounter_controller.apply_resolution(enc_resolution)
                self.last_encounter_resolution = enc_resolution.to_dict()

                # Journal meaningful encounter events
                journal_payload = self.encounter_presenter.present_journal_payload(
                    enc_resolution,
                    self.encounter_controller.get_active_encounter(),
                )
                if (
                    journal_payload
                    and hasattr(self, "campaign_memory_core")
                    and self.campaign_memory_core is not None
                ):
                    self.campaign_memory_core.record_encounter_log_entry(
                        encounter_log=journal_payload,
                        tick=self._tick_count,
                        location=scene_summary.get("location"),
                    )

        # Phase 7.7 — record journal entries and refresh memory panels
        # Fix 6: only refresh recap/snapshot when there are meaningful events
        if hasattr(self, "campaign_memory_core") and self.campaign_memory_core is not None:
            self.campaign_memory_core.record_action_resolution(
                resolution=result_dict,
                coherence_core=self.coherence_core,
                social_state_core=self.social_state_core,
                tick=self._tick_count,
            )
            if result_dict.get("events"):
                self.campaign_memory_core.refresh_recap(
                    coherence_core=self.coherence_core,
                    social_state_core=self.social_state_core,
                    creator_canon_state=getattr(self, "creator_canon_state", None),
                    tick=self._tick_count,
                )
                self.campaign_memory_core.refresh_campaign_snapshot(
                    coherence_core=self.coherence_core,
                    social_state_core=self.social_state_core,
                    creator_canon_state=getattr(self, "creator_canon_state", None),
                    tick=self._tick_count,
                )

        # Phase 8.1 — Store latest dialogue response for UX surface
        resolved_meta = result_dict.get("resolved_action", {}).get("metadata", {})
        if resolved_meta.get("dialogue_response"):
            self.last_dialogue_response = resolved_meta["dialogue_response"]
        else:
            self.last_dialogue_response = None

        # Phase 8.1 — Record dialogue log entry into journal if meaningful
        # Use the same scene_summary captured at resolution time to avoid drift
        dialogue_log = resolved_meta.get("dialogue_log_entry")
        if (
            dialogue_log
            and hasattr(self, "campaign_memory_core")
            and self.campaign_memory_core is not None
        ):
            self.campaign_memory_core.record_dialogue_log_entry(
                dialogue_log=dialogue_log,
                tick=self._tick_count,
                location=scene_summary.get("location"),
            )

        # Phase 8.3 — Advance world simulation after all authoritative updates.
        # NOTE: world sim produces overlay summaries/effects only; it is not
        # a direct mutator of canonical coherence/social/memory truth.
        self.last_world_sim_result = None
        if hasattr(self, "world_sim_controller") and self.world_sim_controller is not None:
            world_result = self.world_sim_controller.advance(
                coherence_core=self.coherence_core,
                social_state_core=self.social_state_core,
                arc_control_controller=getattr(self, "arc_control_controller", None),
                campaign_memory_core=getattr(self, "campaign_memory_core", None),
                encounter_controller=getattr(self, "encounter_controller", None),
                tick=self._tick_count,
            )
            self.last_world_sim_result = world_result.to_dict()

            # Journal meaningful world simulation effects
            if (
                world_result.journal_payloads
                and hasattr(self, "campaign_memory_core")
                and self.campaign_memory_core is not None
            ):
                for journal_effect in world_result.journal_payloads:
                    self.campaign_memory_core.record_world_sim_log_entry(
                        world_effect=journal_effect,
                        tick=self._tick_count,
                        location=scene_summary.get("location"),
                    )

        # Phase 8.4 — Store last subsystem traces for debug inspection
        self.last_action_result = result_dict
        self.last_dialogue_trace = resolved_meta.get("dialogue_trace")

        # Phase 8.4 — Build GM debug inspection bundle (read-only, late in flow).
        # Debug payloads must remain deterministic; IDs are derived from stable
        # tick/choice/context inputs, never randomness.
        self.last_debug_bundle = self._build_debug_bundle(
            scene_summary=scene_summary,
            action_result=result_dict,
        )

        return {
            "ok": True,
            "resolution": result_dict,
            "scene_summary": scene_summary,
        }

    def _build_encounter_participants(self, scene_summary: dict) -> list[dict]:
        """Build participant dicts from scene_summary for encounter start."""
        participants: list[dict] = [{"entity_id": "player", "role": "player"}]
        present_actors = scene_summary.get("present_actors", [])
        for actor in present_actors:
            if isinstance(actor, str) and actor != "player":
                participants.append({"entity_id": actor, "role": "neutral"})
            elif isinstance(actor, dict):
                eid = actor.get("entity_id", actor.get("id", ""))
                if eid and eid != "player":
                    participants.append({
                        "entity_id": eid,
                        "role": actor.get("role", "neutral"),
                    })
        return participants

    def _emit_action_resolution_events(self, result: dict) -> None:
        """Emit resolved action events into the EventBus."""
        from .event_bus import Event
        for event_data in result.get("events", []):
            self.event_bus.emit(
                Event(
                    type=event_data.get("type", "unknown"),
                    payload=dict(event_data.get("payload", {})),
                    source="action_resolver",
                )
            )

    # ------------------------------------------------------------------
    # Phase 8.4 — Debug bundle builder (read-only, no mutation)
    # ------------------------------------------------------------------

    def _build_debug_bundle(
        self,
        scene_summary: dict | None = None,
        action_result: dict | None = None,
    ) -> dict:
        """Build a GM debug inspection bundle from current loop state.

        Strictly read-only — called late in resolve_selected_option()
        after all authoritative updates are complete.
        """
        # Gather control output
        ctrl = getattr(self, "gameplay_control_controller", None)
        control_output = None
        if ctrl is not None:
            cs = ctrl.get_last_choice_set()
            if cs is not None:
                control_output = {"choice_set": cs}
        self.last_control_output = control_output

        # Encounter state (read-only)
        enc_state_dict: dict | None = None
        enc_ctrl = getattr(self, "encounter_controller", None)
        if enc_ctrl is not None and enc_ctrl.has_active_encounter():
            enc_obj = enc_ctrl.get_active_encounter()
            if enc_obj is not None:
                enc_state_dict = self.encounter_presenter.present_encounter(enc_obj)

        # World sim state (read-only)
        ws_state_dict: dict | None = None
        ws_ctrl = getattr(self, "world_sim_controller", None)
        ws_pres = getattr(self, "world_sim_presenter", None)
        if ws_ctrl is not None and ws_pres is not None:
            ws_state_dict = ws_pres.present_state(ws_ctrl.get_state())

        # Arc debug summary (read-only)
        arc_summary: dict | None = None
        arc_ctrl = getattr(self, "arc_control_controller", None)
        if arc_ctrl is not None and hasattr(arc_ctrl, "build_debug_summary"):
            arc_summary = arc_ctrl.build_debug_summary()

        # Recovery debug summary (read-only)
        recovery_summary: dict | None = None
        rec_mgr = getattr(self, "recovery_manager", None)
        if rec_mgr is not None and hasattr(rec_mgr, "build_debug_summary"):
            recovery_summary = rec_mgr.build_debug_summary()

        # Pack debug summary (read-only)
        pack_summary: dict | None = None
        pack_reg = getattr(self, "pack_registry", None)
        if pack_reg is not None and hasattr(pack_reg, "build_debug_summary"):
            pack_summary = pack_reg.build_debug_summary()

        return self.debug_core.build_gm_inspection_bundle(
            tick=getattr(self, "_tick_count", None),
            scene_payload=scene_summary,
            action_result=action_result,
            control_output=control_output,
            last_dialogue_response=getattr(self, "last_dialogue_response", None),
            last_dialogue_trace=getattr(self, "last_dialogue_trace", None),
            last_encounter_resolution=getattr(self, "last_encounter_resolution", None),
            last_encounter_state=enc_state_dict,
            last_world_sim_result=getattr(self, "last_world_sim_result", None),
            last_world_sim_state=ws_state_dict,
            arc_debug_summary=arc_summary,
            recovery_debug_summary=recovery_summary,
            pack_debug_summary=pack_summary,
        )
