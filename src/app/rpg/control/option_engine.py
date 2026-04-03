"""Phase 7.2 — Option Engine.

Generates deterministic, priority-ranked choice options from the coherence
core state. Options are biased by pacing and framing state, then normalized
to keep priorities bounded and stable.
"""

from __future__ import annotations

from typing import Any

from .models import ChoiceOption, ChoiceSet, OptionConstraint, PacingState, FramingState


class OptionEngine:
    """Produces a ChoiceSet from coherence, pacing, and framing state."""

    def __init__(self) -> None:
        pass

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

        options = []
        options.extend(self._build_thread_options(coherence_core))
        options.extend(self._build_npc_options(coherence_core))
        options.extend(self._build_location_options(coherence_core))
        options.append(self._build_recap_option())

        options = self._apply_gm_constraints(options, gm_state)
        options = self._apply_focus_bias(options, framing_state)
        options = self._apply_pacing_bias(options, pacing_state)
        options = self._normalize_priorities(options)
        options = self._sort_and_trim(options, limit=limit)

        choice_set = ChoiceSet(
            choice_set_id=self._make_choice_set_id(coherence_core, framing_state),
            title="Available actions",
            prompt="What do you want to do next?",
            options=options,
            source_summary={
                "scene_summary": coherence_core.get_scene_summary(),
            },
            metadata={},
        )
        return choice_set

    def _make_choice_set_id(self, coherence_core: Any, framing_state: FramingState) -> str:
        """Build a stable, deterministic choice-set id from current control state."""
        scene = coherence_core.get_scene_summary() or {}
        location = scene.get("location") or "unknown_location"
        focus_type = framing_state.focus_target_type or "none"
        focus_id = framing_state.focus_target_id or "none"
        return f"choices:{location}:{focus_type}:{focus_id}"

    def _build_thread_options(self, coherence_core: Any) -> list[ChoiceOption]:
        options: list[ChoiceOption] = []
        for thread in coherence_core.get_unresolved_threads():
            thread_id = thread.get("thread_id")
            title = thread.get("title") or thread_id or "thread"
            options.append(
                self._make_option(
                    option_id=f"investigate_thread:{thread_id}",
                    label=f"Investigate: {title}",
                    intent_type="investigate_thread",
                    summary=f"Follow up on thread '{title}'.",
                    target_id=thread_id,
                    tags=["thread", "investigation"],
                    priority=1.0,
                    metadata={
                        "source": "thread",
                        "reason": f"Unresolved thread '{title}' is active.",
                    },
                )
            )
        return options

    def _build_npc_options(self, coherence_core: Any) -> list[ChoiceOption]:
        options: list[ChoiceOption] = []
        for fact in coherence_core.get_state().stable_world_facts.values():
            if str(fact.fact_id).startswith("npc:") and fact.predicate == "name":
                npc_id = fact.subject
                npc_name = fact.value
                options.append(
                    self._make_option(
                        option_id=f"talk_to_npc:{npc_id}",
                        label=f"Talk to {npc_name}",
                        intent_type="talk_to_npc",
                        summary=f"Approach {npc_name} and talk.",
                        target_id=npc_id,
                        tags=["npc", "social"],
                        priority=0.8,
                        metadata={
                            "source": "npc",
                            "reason": f"NPC '{npc_name}' is present in known world state.",
                        },
                    )
                )
        return options

    def _build_location_options(self, coherence_core: Any) -> list[ChoiceOption]:
        options: list[ChoiceOption] = []
        for fact in coherence_core.get_state().stable_world_facts.values():
            if str(fact.fact_id).startswith("location:") and fact.predicate == "name":
                location_id = fact.subject
                location_name = fact.value
                options.append(
                    self._make_option(
                        option_id=f"travel_to_location:{location_id}",
                        label=f"Travel to {location_name}",
                        intent_type="travel_to_location",
                        summary=f"Go to {location_name}.",
                        target_id=location_id,
                        tags=["location", "travel"],
                        priority=0.5,
                        metadata={
                            "source": "location",
                            "reason": f"Location '{location_name}' is available in known world state.",
                        },
                    )
                )
        return options

    def _build_recap_option(self) -> ChoiceOption:
        return self._make_option(
            option_id="request_recap",
            label="Ask for a recap",
            intent_type="request_recap",
            summary="Review the current situation.",
            target_id=None,
            tags=["recap", "status"],
            priority=0.2,
            metadata={
                "source": "recap",
                "reason": "Recap is always available as a fallback control option.",
            },
        )

    def _apply_gm_constraints(self, options: list[ChoiceOption], gm_state: Any) -> list[ChoiceOption]:
        """Apply GM constraints to filter or modify options.

        This v1 implementation preserves all options unless gm_state
        carries explicit filter directives. Extend as needed.
        """
        if gm_state is None:
            return options

        # If gm_state has filter logic, apply it here.
        # For now, we return all options unchanged.
        return options

    def _apply_focus_bias(self, options: list[ChoiceOption], framing_state: FramingState) -> list[ChoiceOption]:
        """Apply multiplicative focus bias to option priorities.

        Focused targets get a boost; non-focused targets get a gentle decay.
        This keeps diversity in the option set instead of letting focus
        dominate entirely.
        """
        focus_type = framing_state.focus_target_type
        focus_id = framing_state.focus_target_id
        if not focus_type or not focus_id:
            return options

        for option in options:
            if option.target_id == focus_id:
                option.priority *= 1.5
                option.metadata.setdefault("biases", [])
                option.metadata["biases"].append("focus_boost")
            else:
                option.priority *= 0.9
                option.metadata.setdefault("biases", [])
                option.metadata["biases"].append("focus_decay")
        return options

    def _apply_pacing_bias(self, options: list[ChoiceOption], pacing_state: PacingState) -> list[ChoiceOption]:
        """Apply pacing-based additive bias to option priorities."""
        for option in options:
            if pacing_state.danger_level == "high" and option.intent_type in {"travel_to_location", "investigate_thread"}:
                option.priority += 0.25
                option.metadata.setdefault("biases", [])
                option.metadata["biases"].append("danger_high")
            if pacing_state.reveal_pressure == "high" and option.intent_type == "investigate_thread":
                option.priority += 0.5
                option.metadata.setdefault("biases", [])
                option.metadata["biases"].append("reveal_pressure_high")
            if pacing_state.social_pressure == "high" and option.intent_type == "talk_to_npc":
                option.priority += 0.35
                option.metadata.setdefault("biases", [])
                option.metadata["biases"].append("social_pressure_high")
        return options

    def _normalize_priorities(self, options: list[ChoiceOption]) -> list[ChoiceOption]:
        """Normalize priorities to a stable 0..1-ish range before sorting.

        This prevents stacked biasing from causing runaway values and helps keep
        ordering stable as the control layer grows more complex.
        """
        if not options:
            return options
        max_priority = max((o.priority for o in options), default=1.0) or 1.0
        for option in options:
            option.priority = option.priority / max_priority
        return options

    def _sort_and_trim(self, options: list[ChoiceOption], limit: int = 6) -> list[ChoiceOption]:
        """Sort options by priority (descending), then by intent_type and option_id for stability."""
        options = sorted(
            options,
            key=lambda o: (-o.priority, o.intent_type, o.option_id),
        )
        return options[:limit]

    def _make_option(
        self,
        option_id: str,
        label: str,
        intent_type: str,
        summary: str,
        target_id: str | None,
        tags: list[str] | None = None,
        priority: float = 0.5,
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
            metadata=dict(metadata or {}),
        )