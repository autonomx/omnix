"""Generate structured player options from coherence + creator/GM state."""

from __future__ import annotations

import uuid
from typing import Any

from .models import ChoiceOption, ChoiceSet, FramingState, OptionConstraint, PacingState


class OptionEngine:
    """Deterministic option generation from coherence + GM state."""

    def __init__(self) -> None:
        pass

    def build_choice_set(
        self,
        coherence_core: Any,
        gm_state: Any,
        pacing_state: PacingState,
        framing_state: FramingState,
    ) -> ChoiceSet:
        options: list[ChoiceOption] = []

        options.extend(self._build_thread_options(coherence_core))
        options.extend(self._build_npc_options(coherence_core))
        options.extend(self._build_location_options(coherence_core))
        options.append(self._build_recap_option())

        options = self._apply_gm_constraints(options, gm_state)
        options = self._apply_focus_bias(options, framing_state)
        options = self._apply_pacing_bias(options, pacing_state)
        options = self._sort_and_trim(options)

        choice_set_id = f"cs:{uuid.uuid4().hex[:8]}"
        return ChoiceSet(
            choice_set_id=choice_set_id,
            title="What do you do?",
            prompt="Choose your next action.",
            options=options,
            source_summary={
                "thread_count": len(self._build_thread_options(coherence_core)),
                "npc_count": len(self._build_npc_options(coherence_core)),
                "location_count": len(self._build_location_options(coherence_core)),
            },
        )

    # ------------------------------------------------------------------
    # Option builders
    # ------------------------------------------------------------------

    def _build_thread_options(self, coherence_core: Any) -> list[ChoiceOption]:
        options: list[ChoiceOption] = []
        threads = coherence_core.get_unresolved_threads()
        if not isinstance(threads, list):
            return options
        for thread in threads:
            if isinstance(thread, dict):
                thread_id = thread.get("thread_id", "")
                title = thread.get("title", "unknown thread")
                priority = thread.get("priority", "normal")
            else:
                thread_id = getattr(thread, "thread_id", "")
                title = getattr(thread, "title", "unknown thread")
                priority = getattr(thread, "priority", "normal")
            prio_val = {"critical": 3.0, "high": 2.0, "normal": 1.0, "low": 0.5}.get(
                priority, 1.0
            )
            options.append(
                self._make_option(
                    option_id=f"opt:thread:{thread_id}",
                    label=f"Investigate: {title}",
                    intent_type="investigate_thread",
                    summary=f"Follow up on the unresolved thread: {title}",
                    target_id=thread_id,
                    tags=["thread", priority],
                    priority=prio_val,
                )
            )
        return options

    def _build_npc_options(self, coherence_core: Any) -> list[ChoiceOption]:
        options: list[ChoiceOption] = []
        scene = coherence_core.get_scene_summary()
        if not isinstance(scene, dict):
            return options
        actors = scene.get("present_actors", [])
        for actor_id in actors:
            options.append(
                self._make_option(
                    option_id=f"opt:npc:{actor_id}",
                    label=f"Talk to {actor_id}",
                    intent_type="talk_to_npc",
                    summary=f"Speak with {actor_id} in the current scene.",
                    target_id=actor_id,
                    tags=["npc", "social"],
                    priority=1.0,
                )
            )
        return options

    def _build_location_options(self, coherence_core: Any) -> list[ChoiceOption]:
        options: list[ChoiceOption] = []
        scene = coherence_core.get_scene_summary()
        if not isinstance(scene, dict):
            return options
        location = scene.get("location")
        if location:
            options.append(
                self._make_option(
                    option_id=f"opt:loc:{location}",
                    label=f"Explore {location}",
                    intent_type="travel_to_location",
                    summary=f"Explore the current location: {location}.",
                    target_id=location,
                    tags=["location", "explore"],
                    priority=0.8,
                )
            )
        return options

    def _build_recap_option(self) -> ChoiceOption:
        return self._make_option(
            option_id="opt:recap",
            label="Request recap",
            intent_type="request_recap",
            summary="Get a summary of recent events and current situation.",
            tags=["meta", "recap"],
            priority=0.3,
        )

    # ------------------------------------------------------------------
    # Constraint / bias application
    # ------------------------------------------------------------------

    def _apply_gm_constraints(
        self, options: list[ChoiceOption], gm_state: Any
    ) -> list[ChoiceOption]:
        if gm_state is None:
            return options
        pinned_threads: list[str] = []
        for directive in gm_state.get_active_directives():
            dtype = getattr(directive, "directive_type", "")
            if dtype == "pin_thread":
                pinned_threads.append(getattr(directive, "thread_id", ""))
        for opt in options:
            if opt.intent_type == "investigate_thread" and opt.target_id in pinned_threads:
                opt.priority += 2.0
                opt.constraints.append(
                    OptionConstraint(
                        constraint_id=f"gc:pin:{opt.target_id}",
                        constraint_type="gm_pin",
                        value="boosted",
                        source="gm_directive",
                    )
                )
        return options

    def _apply_focus_bias(
        self, options: list[ChoiceOption], framing_state: FramingState
    ) -> list[ChoiceOption]:
        if not framing_state.focus_target_id:
            return options
        for opt in options:
            if opt.target_id == framing_state.focus_target_id:
                opt.priority += 1.5
                opt.tags.append("focused")
        return options

    def _apply_pacing_bias(
        self, options: list[ChoiceOption], pacing_state: PacingState
    ) -> list[ChoiceOption]:
        for opt in options:
            if pacing_state.danger_level == "high" and "thread" in opt.tags:
                opt.priority += 0.5
            if pacing_state.reveal_pressure == "high" and opt.intent_type == "investigate_thread":
                opt.priority += 0.5
            if pacing_state.social_pressure == "high" and "social" in opt.tags:
                opt.priority += 0.5
        return options

    def _sort_and_trim(
        self, options: list[ChoiceOption], limit: int = 6
    ) -> list[ChoiceOption]:
        options.sort(key=lambda o: o.priority, reverse=True)
        return options[:limit]

    def _make_option(
        self,
        option_id: str,
        label: str,
        intent_type: str,
        summary: str,
        target_id: str | None = None,
        tags: list[str] | None = None,
        priority: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> ChoiceOption:
        return ChoiceOption(
            option_id=option_id,
            label=label,
            intent_type=intent_type,
            summary=summary,
            target_id=target_id,
            tags=tags or [],
            priority=priority,
            metadata=metadata or {},
        )
