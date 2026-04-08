"""Phase 7.2 — Option Engine.

Generates deterministic, priority-ranked choice options from the coherence
core state. Options are biased by pacing and framing state, then normalized
for stability.
"""

from __future__ import annotations

from typing import Any

from .models import (
    ChoiceOption,
    ChoiceSet,
    FramingState,
    OptionConstraint,
    PacingState,
)


class OptionEngine:
    """Produces a ChoiceSet from coherence, pacing, and framing state."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_choice_set(
        self,
        coherence_core: Any,
        gm_state: Any,
        pacing_state: PacingState | None = None,
        framing_state: FramingState | None = None,
        limit: int = 6,
    ) -> ChoiceSet:
        pacing_state = pacing_state or PacingState()
        framing_state = framing_state or FramingState()

        options: list[ChoiceOption] = []

        # --- Build base options ---
        thread_opts = self._build_thread_options(coherence_core)
        npc_opts = self._build_npc_options(coherence_core)
        loc_opts = self._build_location_options(coherence_core)

        options.extend(thread_opts)
        options.extend(npc_opts)
        options.extend(loc_opts)
        options.append(self._build_recap_option())

        # --- Apply transformations ---
        options = self._apply_gm_constraints(options, gm_state)
        options = self._apply_focus_bias(options, framing_state)
        options = self._apply_pacing_bias(options, pacing_state)

        options = self._normalize_priorities(options)
        options = self._sort_and_trim(options, limit=limit)

        # --- Build choice set ---
        return ChoiceSet(
            choice_set_id=self._make_choice_set_id(coherence_core, framing_state),
            title="What do you do?",
            prompt="Choose your next action.",
            options=options,
            source_summary={
                "thread_count": len(thread_opts),
                "npc_count": len(npc_opts),
                "location_count": len(loc_opts),
            },
            metadata={},
        )

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_choice_set_id(self, coherence_core: Any, framing_state: FramingState) -> str:
        """Deterministic ID for replay + diff stability."""
        try:
            scene = coherence_core.get_scene_summary() or {}
            location = scene.get("location") or "unknown"
        except Exception:
            location = "unknown"

        focus_type = framing_state.focus_target_type or "none"
        focus_id = framing_state.focus_target_id or "none"

        return f"choices:{location}:{focus_type}:{focus_id}"

    # ------------------------------------------------------------------
    # Option builders
    # ------------------------------------------------------------------

    def _build_thread_options(self, coherence_core: Any) -> list[ChoiceOption]:
        options: list[ChoiceOption] = []

        threads = []
        if hasattr(coherence_core, "get_unresolved_threads"):
            threads = coherence_core.get_unresolved_threads() or []

        for thread in threads:
            thread_id = getattr(thread, "thread_id", None) or thread.get("thread_id")
            title = getattr(thread, "title", None) or thread.get("title") or thread_id

            priority_map = {"critical": 3.0, "high": 2.0, "normal": 1.0, "low": 0.5}
            raw_priority = getattr(thread, "priority", None) or thread.get("priority", "normal")
            base_priority = priority_map.get(raw_priority, 1.0)

            options.append(
                self._make_option(
                    option_id=f"investigate_thread:{thread_id}",
                    label=f"Investigate: {title}",
                    intent_type="investigate_thread",
                    summary=f"Follow up on '{title}'.",
                    target_id=thread_id,
                    tags=["thread", raw_priority],
                    priority=base_priority,
                    resolution_type="thread_progress",
                    metadata={"source": "thread"},
                )
            )
        return options

    def _build_npc_options(self, coherence_core: Any) -> list[ChoiceOption]:
        options: list[ChoiceOption] = []

        # --- Try scene-based actors (copilot style)
        try:
            scene = coherence_core.get_scene_summary()
            if isinstance(scene, dict):
                for actor_id in scene.get("present_actors", []):
                    options.append(
                        self._make_option(
                            option_id=f"talk_to_npc:{actor_id}",
                            label=f"Talk to {actor_id}",
                            intent_type="talk_to_npc",
                            summary=f"Speak with {actor_id}.",
                            target_id=actor_id,
                            tags=["npc", "social"],
                            priority=1.0,
                            resolution_type="social_contact",
                            metadata={"source": "scene"},
                        )
                    )
        except Exception:
            pass

        # --- Try fact-based (roleplay5 style)
        try:
            state = coherence_core.get_state()
            for fact in getattr(state, "stable_world_facts", {}).values():
                if str(fact.fact_id).startswith("npc:") and fact.predicate == "name":
                    npc_id = fact.subject
                    npc_name = fact.value
                    options.append(
                        self._make_option(
                            option_id=f"talk_to_npc:{npc_id}",
                            label=f"Talk to {npc_name}",
                            intent_type="talk_to_npc",
                            summary=f"Talk to {npc_name}.",
                            target_id=npc_id,
                            tags=["npc", "social"],
                            priority=0.8,
                            resolution_type="social_contact",
                            metadata={"source": "facts"},
                        )
                    )
        except Exception:
            pass

        return options

    def _build_location_options(self, coherence_core: Any) -> list[ChoiceOption]:
        options: list[ChoiceOption] = []

        # Scene-based
        try:
            scene = coherence_core.get_scene_summary()
            if isinstance(scene, dict) and scene.get("location"):
                loc = scene["location"]
                options.append(
                    self._make_option(
                        option_id=f"explore:{loc}",
                        label=f"Explore {loc}",
                        intent_type="travel_to_location",
                        summary=f"Explore {loc}.",
                        target_id=loc,
                        tags=["location"],
                        priority=0.8,
                        resolution_type="location_travel",
                        metadata={"source": "scene"},
                    )
                )
        except Exception:
            pass

        return options

    def _build_recap_option(self) -> ChoiceOption:
        return self._make_option(
            option_id="request_recap",
            label="Request recap",
            intent_type="request_recap",
            summary="Review the current situation.",
            target_id=None,
            tags=["meta"],
            priority=0.2,
            resolution_type="recap",
            metadata={"source": "system"},
        )

    # ------------------------------------------------------------------
    # Bias + constraints
    # ------------------------------------------------------------------

    def _apply_gm_constraints(self, options: list[ChoiceOption], gm_state: Any) -> list[ChoiceOption]:
        if gm_state is None:
            return options

        # Example: pin thread boost
        for directive in getattr(gm_state, "get_active_directives", lambda: [])():
            if getattr(directive, "directive_type", "") == "pin_thread":
                thread_id = getattr(directive, "thread_id", None)
                for opt in options:
                    if opt.target_id == thread_id:
                        opt.priority += 2.0
                        opt.constraints.append(
                            OptionConstraint(
                                constraint_id=f"pin:{thread_id}",
                                condition="gm_pin",
                                required_value=True,
                            )
                        )
        return options

    def _apply_focus_bias(self, options: list[ChoiceOption], framing_state: FramingState) -> list[ChoiceOption]:
        focus_id = framing_state.focus_target_id
        if not focus_id:
            return options

        for opt in options:
            opt.metadata.setdefault("biases", [])
            if opt.target_id == focus_id:
                opt.priority *= 1.5
                opt.metadata["biases"].append("focus_boost")
            else:
                opt.priority *= 0.9
                opt.metadata["biases"].append("focus_decay")
        return options

    def _apply_pacing_bias(self, options: list[ChoiceOption], pacing_state: PacingState) -> list[ChoiceOption]:
        for opt in options:
            opt.metadata.setdefault("biases", [])

            if pacing_state.danger_level == "high" and "thread" in opt.tags:
                opt.priority += 0.5
                opt.metadata["biases"].append("danger")

            if pacing_state.reveal_pressure == "high" and opt.intent_type == "investigate_thread":
                opt.priority += 0.5
                opt.metadata["biases"].append("reveal")

            if pacing_state.social_pressure == "high" and "social" in opt.tags:
                opt.priority += 0.5
                opt.metadata["biases"].append("social")

        return options

    def _normalize_priorities(self, options: list[ChoiceOption]) -> list[ChoiceOption]:
        if not options:
            return options

        max_p = max(o.priority for o in options) or 1.0
        for opt in options:
            opt.priority /= max_p
        return options

    def _sort_and_trim(self, options: list[ChoiceOption], limit: int = 6) -> list[ChoiceOption]:
        return sorted(
            options,
            key=lambda o: (-o.priority, o.intent_type, o.option_id),
        )[:limit]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_option(
        self,
        option_id: str,
        label: str,
        intent_type: str,
        summary: str,
        target_id: str | None,
        tags: list[str] | None = None,
        priority: float = 0.5,
        resolution_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChoiceOption:
        return ChoiceOption(
            option_id=option_id,
            label=label,
            intent_type=intent_type,
            summary=summary,
            target_id=target_id,
            tags=list(tags or []),
            constraints=[],
            priority=priority,
            resolution_type=resolution_type,
            metadata=dict(metadata or {}),
        )