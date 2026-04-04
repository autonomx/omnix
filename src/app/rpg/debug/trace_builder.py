"""Phase 8.4 — Debug Trace Builder.

Build stable, system-specific debug traces from existing metadata/state.
Pure read-only builder logic — consumes traces, does not create new truth.
"""

from __future__ import annotations

from typing import Any

from .models import (
    ChoiceExplanation,
    DebugTrace,
    DebugTraceNode,
    EncounterExplanation,
    GMInspectionBundle,
    NPCResponseExplanation,
    WorldSimExplanation,
)


# Maximum items in bounded lists to avoid payload bloat
_MAX_REASONS = 20
_MAX_EFFECTS = 50
_MAX_WARNINGS = 30


class DebugTraceBuilder:
    """Build deterministic debug traces from existing subsystem outputs.

    This builder is read-only.  If a reason or trace detail is missing
    from the source data, it reports ``"unavailable"`` rather than
    fabricating explanations.

    All IDs are derived from stable inputs (tick, option_id, key) so that
    replay of the same inputs produces identical debug payloads.
    """

    # ------------------------------------------------------------------
    # Stable ID helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _stable_part(value: object) -> str:
        """Convert a value to a stable, ID-safe string fragment."""
        if value is None:
            return "none"
        text = str(value).strip().lower()
        if not text:
            return "empty"
        # Replace characters unsafe for IDs
        return text.replace(" ", "_")

    @classmethod
    def _trace_id(
        cls,
        scope: str,
        tick: int | None = None,
        key: str | None = None,
    ) -> str:
        """Build a deterministic trace ID."""
        tick_part = str(tick) if tick is not None else "none"
        key_part = cls._stable_part(key)
        return f"debug-trace:{cls._stable_part(scope)}:{tick_part}:{key_part}"

    @classmethod
    def _node_id(
        cls,
        scope: str,
        node_type: str,
        index: int,
        key: str | None = None,
    ) -> str:
        """Build a deterministic node ID."""
        key_part = cls._stable_part(key)
        return (
            f"debug-node:{cls._stable_part(scope)}:"
            f"{cls._stable_part(node_type)}:{index}:{key_part}"
        )

    # ------------------------------------------------------------------
    # Choice trace
    # ------------------------------------------------------------------

    def build_choice_trace(
        self, control_output: dict, tick: int | None = None
    ) -> DebugTrace:
        """Build a debug trace for choice generation.

        *control_output* is the dict returned by
        ``GameplayControlController.build_control_output()``.
        """
        nodes: list[DebugTraceNode] = []
        warnings: list[str] = []

        choice_set = control_output.get("choice_set", {})
        options = choice_set.get("options", [])

        # Build a stable key from sorted option IDs
        choice_key = ",".join(
            sorted(
                str(opt.get("option_id", ""))
                for opt in options
                if isinstance(opt, dict)
            )
        )
        trace_id = self._trace_id("choice", tick=tick, key=choice_key)

        for index, opt in enumerate(options):
            reasons = self._extract_choice_reasons(opt)
            opt_key = opt.get("option_id") if isinstance(opt, dict) else None
            node = DebugTraceNode(
                node_id=self._node_id("choice", "choice_generation", index, key=opt_key),
                node_type="choice_generation",
                title=opt.get("label", ""),
                summary=opt.get("summary", opt.get("description", "")),
                inputs={
                    "intent_type": opt.get("intent_type", opt.get("type", "")),
                    "target_id": opt.get("target_id"),
                    "tags": list(opt.get("tags", [])),
                },
                outputs={
                    "priority": opt.get("priority", 0.0),
                    "selected": opt.get("selected", False),
                },
                reasons=reasons,
                metadata={
                    k: v
                    for k, v in opt.get("metadata", {}).items()
                    if k.startswith("debug_") or k in (
                        "encounter_start", "source_system",
                    )
                },
            )
            nodes.append(node)

        # Pacing / framing context
        pacing = control_output.get("pacing", {})
        framing = control_output.get("framing", {})
        external_bias = control_output.get("external_bias", {})

        if pacing or framing or external_bias:
            ctx_node = DebugTraceNode(
                node_id=self._node_id(
                    "choice",
                    "control_context",
                    len(options),
                    key="pacing_framing_bias",
                ),
                node_type="choice_generation",
                title="Control Context",
                summary="Pacing, framing, and bias context for choice generation",
                inputs={
                    "pacing": dict(pacing) if pacing else {},
                    "framing": dict(framing) if framing else {},
                    "external_bias": dict(external_bias) if external_bias else {},
                },
                outputs={},
                reasons=[],
            )
            nodes.append(ctx_node)

        return DebugTrace(
            trace_id=trace_id,
            tick=tick,
            scope="choice",
            nodes=nodes,
            warnings=self._normalize_warning_list(warnings),
        )

    # ------------------------------------------------------------------
    # Action trace
    # ------------------------------------------------------------------

    def build_action_trace(
        self, action_result: dict, tick: int | None = None
    ) -> DebugTrace:
        """Build a debug trace for action resolution.

        *action_result* is the dict from ``ActionResolver.resolve_choice()``.
        """
        nodes: list[DebugTraceNode] = []
        warnings: list[str] = []

        resolved = action_result.get("resolved_action", {})
        events = action_result.get("events", [])
        trace_data = action_result.get("trace", {})

        # Build a stable key from the resolved action
        result_key = (
            resolved.get("option_id")
            or resolved.get("action_id")
            or resolved.get("intent_type", "")
        )
        trace_id = self._trace_id("action", tick=tick, key=result_key)

        # 1. Selected choice → mapped action
        meta = resolved.get("metadata", {})
        reasons = self._extract_execution_reasons(resolved, trace_data)

        nodes.append(DebugTraceNode(
            node_id=self._node_id(
                "action",
                "action_resolution",
                0,
                key=resolved.get("action_id") or resolved.get("option_id"),
            ),
            node_type="action_resolution",
            title=f"Action: {resolved.get('intent_type', 'unknown')}",
            summary=resolved.get("summary", ""),
            inputs={
                "option_id": resolved.get("option_id", ""),
                "intent_type": resolved.get("intent_type", ""),
                "target_id": resolved.get("target_id"),
            },
            outputs={
                "outcome": resolved.get("outcome", ""),
                "event_count": len(events),
                "has_transition": resolved.get("transition") is not None,
            },
            reasons=reasons,
            metadata={
                "mapped_action": meta.get("mapped_action"),
                "evaluation": meta.get("evaluation"),
                "constraint_evaluation": meta.get("constraint_evaluation"),
                "encounter_mode": meta.get("encounter_mode"),
                "encounter_action_type": meta.get("encounter_action_type"),
            },
        ))

        # 2. Dialogue attachment
        dialogue_response = meta.get("dialogue_response")
        if dialogue_response:
            dialogue_reasons = self._extract_dialogue_reasons(
                dialogue_response, meta.get("dialogue_trace", {})
            )
            nodes.append(DebugTraceNode(
                node_id=self._node_id(
                    "action",
                    "dialogue_planning",
                    1,
                    key=dialogue_response.get("act"),
                ),
                node_type="dialogue_planning",
                title=f"Dialogue: {dialogue_response.get('act', 'unknown')}",
                summary=dialogue_response.get("summary", ""),
                inputs={
                    "speaker_id": dialogue_response.get("speaker_id", ""),
                    "listener_id": dialogue_response.get("listener_id"),
                },
                outputs={
                    "act": dialogue_response.get("act", ""),
                    "tone": dialogue_response.get("tone", ""),
                    "stance": dialogue_response.get("stance", ""),
                },
                reasons=dialogue_reasons,
            ))

        # 3. Encounter context if present
        enc_id = meta.get("encounter_id")
        if enc_id:
            nodes.append(DebugTraceNode(
                node_id=self._node_id(
                    "action",
                    "encounter_resolution",
                    2,
                    key=enc_id,
                ),
                node_type="encounter_resolution",
                title=f"Encounter context: {meta.get('encounter_mode', 'unknown')}",
                summary=f"Action within {meta.get('encounter_mode', '')} encounter",
                inputs={
                    "encounter_id": enc_id,
                    "encounter_mode": meta.get("encounter_mode"),
                },
                outputs={
                    "encounter_action_type": meta.get("encounter_action_type"),
                    "encounter_tags": meta.get("encounter_tags", []),
                },
                reasons=[],
            ))

        # 4. Event summary
        if events:
            event_types: dict[str, int] = {}
            for evt in events:
                etype = evt.get("event_type", "unknown")
                event_types[etype] = event_types.get(etype, 0) + 1
            nodes.append(DebugTraceNode(
                node_id=self._node_id(
                    "action",
                    "emitted_events",
                    3,
                    key="events_summary",
                ),
                node_type="action_resolution",
                title="Emitted Events",
                summary=f"{len(events)} events emitted",
                inputs={},
                outputs={"event_type_counts": event_types},
                reasons=[],
            ))

        return DebugTrace(
            trace_id=trace_id,
            tick=tick,
            scope="action",
            nodes=nodes,
            warnings=self._normalize_warning_list(warnings),
        )

    # ------------------------------------------------------------------
    # Dialogue explanation
    # ------------------------------------------------------------------

    def build_dialogue_explanation(
        self,
        dialogue_response: dict,
        dialogue_trace: dict,
    ) -> NPCResponseExplanation:
        """Build an NPC response explanation from dialogue outputs."""
        trace = dialogue_trace or {}
        reasons = self._extract_dialogue_reasons(dialogue_response, trace)

        state_drivers = trace.get("state_drivers", {})
        reveal_policy = trace.get("reveal_policy", {})

        # Derive blocked/allowed topics from reveal policy
        blocked: list[str] = []
        allowed: list[str] = []
        if isinstance(reveal_policy, dict):
            blocked = list(reveal_policy.get("blocked_topics", []))
            allowed = list(reveal_policy.get("allowed_topics", []))
            # If specific fields not present, check for suppress/permit markers
            if not blocked:
                blocked = list(reveal_policy.get("suppressed", []))
            if not allowed:
                allowed = list(reveal_policy.get("permitted", []))

        return NPCResponseExplanation(
            speaker_id=dialogue_response.get("speaker_id", ""),
            listener_id=dialogue_response.get("listener_id"),
            act=dialogue_response.get("act", ""),
            tone=dialogue_response.get("tone", ""),
            stance=dialogue_response.get("stance", ""),
            drivers=dict(state_drivers) if state_drivers else {},
            reasons=reasons,
            blocked_topics=blocked,
            allowed_topics=allowed,
            metadata={
                "reveal_policy": dict(reveal_policy) if reveal_policy else {},
            },
        )

    # ------------------------------------------------------------------
    # Encounter explanation
    # ------------------------------------------------------------------

    def build_encounter_explanation(
        self,
        encounter_state: dict,
        encounter_trace: dict | None = None,
    ) -> EncounterExplanation:
        """Build an encounter explanation from state and trace."""
        trace = encounter_trace or {}
        reasons = self._extract_encounter_reasons(encounter_state, trace)

        return EncounterExplanation(
            encounter_id=encounter_state.get("encounter_id"),
            mode=encounter_state.get("mode") or trace.get("mode"),
            outcome_type=trace.get("outcome_type", ""),
            drivers={
                "pressure": encounter_state.get("pressure"),
                "stakes": encounter_state.get("stakes"),
                "status": encounter_state.get("status"),
                "round_index": encounter_state.get("round_index"),
            },
            reasons=reasons,
            participant_updates=[
                dict(u) for u in trace.get("participant_updates", [])
            ],
            objective_updates=[
                dict(u) for u in trace.get("objective_updates", [])
            ],
            metadata={
                "state_updates": trace.get("state_updates", {}),
            },
        )

    # ------------------------------------------------------------------
    # World sim explanation
    # ------------------------------------------------------------------

    def build_world_sim_explanation(
        self,
        world_result: dict,
        world_state: dict | None = None,
    ) -> WorldSimExplanation:
        """Build a world-sim explanation from result and optional state."""
        reasons = self._extract_world_reasons(world_result, world_state)

        effects = world_result.get("generated_effects", [])
        # Classify effects by type
        effect_summaries: list[dict[str, Any]] = []
        pressure_changes: list[dict[str, Any]] = []
        rumor_changes: list[dict[str, Any]] = []
        location_changes: list[dict[str, Any]] = []

        for eff in effects[:_MAX_EFFECTS]:
            etype = eff.get("effect_type", "")
            summary = {
                "effect_type": etype,
                "scope": eff.get("scope", ""),
                "target_id": eff.get("target_id"),
            }
            effect_summaries.append(summary)

            if etype == "thread_pressure_changed":
                pressure_changes.append(summary)
            elif etype in ("rumor_spread", "rumor_cools"):
                rumor_changes.append(summary)
            elif etype == "location_condition_changed":
                location_changes.append(summary)

        return WorldSimExplanation(
            sim_tick=world_result.get("tick", 0),
            effects=effect_summaries,
            pressure_changes=pressure_changes,
            rumor_changes=rumor_changes,
            location_changes=location_changes,
            reasons=reasons,
            metadata={
                "advanced": world_result.get("advanced", False),
                "total_effect_count": len(effects),
            },
        )

    # ------------------------------------------------------------------
    # GM inspection bundle
    # ------------------------------------------------------------------

    def build_gm_bundle(
        self,
        tick: int | None = None,
        scene_payload: dict | None = None,
        action_result: dict | None = None,
        control_output: dict | None = None,
        last_dialogue_response: dict | None = None,
        last_dialogue_trace: dict | None = None,
        last_encounter_resolution: dict | None = None,
        last_encounter_state: dict | None = None,
        last_world_sim_result: dict | None = None,
        last_world_sim_state: dict | None = None,
        arc_debug_summary: dict | None = None,
        recovery_debug_summary: dict | None = None,
        pack_debug_summary: dict | None = None,
    ) -> GMInspectionBundle:
        """Build a full GM inspection bundle from available data.

        All parameters are optional.  Missing data results in empty
        sections — never fabricated explanations.
        """
        warnings: list[str] = []

        # Scene
        scene = dict(scene_payload) if scene_payload else {}

        # Choice explanations
        choice_explanations: list[ChoiceExplanation] = []
        if control_output:
            choice_set = control_output.get("choice_set", {})
            for opt in choice_set.get("options", []):
                reasons = self._extract_choice_reasons(opt)
                constraints = [
                    c.get("constraint_type", str(c))
                    if isinstance(c, dict)
                    else str(c)
                    for c in opt.get("constraints", [])
                ]
                related = []
                opt_meta = opt.get("metadata", {})
                if opt_meta.get("encounter_start"):
                    related.append("encounter")
                if opt_meta.get("debug_source"):
                    related.append(opt_meta["debug_source"])
                choice_explanations.append(ChoiceExplanation(
                    choice_id=opt.get("option_id", ""),
                    label=opt.get("label", ""),
                    source=opt_meta.get("debug_source", "standard"),
                    priority=str(opt.get("priority", 0.0)),
                    reasons=reasons,
                    constraints=constraints,
                    related_systems=related,
                ))

        # Dialogue explanation
        dialogue_explanation: dict[str, Any] = {}
        if last_dialogue_response:
            npc_expl = self.build_dialogue_explanation(
                last_dialogue_response,
                last_dialogue_trace or {},
            )
            dialogue_explanation = npc_expl.to_dict()

        # Encounter explanation
        encounter_explanation: dict[str, Any] = {}
        enc_source = last_encounter_state or {}
        enc_trace = last_encounter_resolution or {}
        if enc_source or enc_trace:
            enc_expl = self.build_encounter_explanation(enc_source, enc_trace)
            encounter_explanation = enc_expl.to_dict()

        # World explanation
        world_explanation: dict[str, Any] = {}
        if last_world_sim_result:
            world_expl = self.build_world_sim_explanation(
                last_world_sim_result,
                last_world_sim_state,
            )
            world_explanation = world_expl.to_dict()

        # Arc explanation
        arc_explanation = dict(arc_debug_summary) if arc_debug_summary else {}

        # Recovery events
        recovery_events: list[dict[str, Any]] = []
        if recovery_debug_summary:
            for rec in recovery_debug_summary.get("recent_recoveries", []):
                recovery_events.append(dict(rec))
            for w in recovery_debug_summary.get("warnings", []):
                warnings.append(str(w))

        # Pack info
        pack_meta: dict[str, Any] = {}
        if pack_debug_summary:
            pack_meta = dict(pack_debug_summary)

        metadata: dict[str, Any] = {}
        if pack_meta:
            metadata["packs"] = pack_meta

        return GMInspectionBundle(
            tick=tick,
            scene=scene,
            choice_explanations=choice_explanations,
            dialogue_explanation=dialogue_explanation,
            encounter_explanation=encounter_explanation,
            world_explanation=world_explanation,
            arc_explanation=arc_explanation,
            recovery_events=recovery_events,
            warnings=self._normalize_warning_list(warnings),
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Internal helpers — reason extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_choice_reasons(option: dict) -> list[str]:
        """Extract reasons for why a choice was offered."""
        reasons: list[str] = []
        meta = option.get("metadata", {})

        # Explicit debug reasons
        debug_reasons = meta.get("debug_reasons", [])
        if isinstance(debug_reasons, list):
            reasons.extend(str(r) for r in debug_reasons)

        # Source system
        source = meta.get("debug_source", "")
        if source:
            reasons.append(f"Source: {source}")

        # Encounter start
        if meta.get("encounter_start"):
            reasons.append(
                f"Starts encounter: {meta['encounter_start']}"
            )

        # Priority
        priority = option.get("priority", 0.0)
        if priority:
            reasons.append(f"Priority: {priority}")

        # Constraints
        constraints = option.get("constraints", [])
        if constraints:
            reasons.append(f"Constraints: {len(constraints)} applied")

        if not reasons:
            reasons.append("Standard option generation")

        return reasons[:_MAX_REASONS]

    @staticmethod
    def _extract_execution_reasons(
        resolved: dict, trace: dict
    ) -> list[str]:
        """Extract reasons from a resolved action and its trace."""
        reasons: list[str] = []
        meta = resolved.get("metadata", {})

        # Mapped action
        mapped = meta.get("mapped_action")
        if mapped:
            reasons.append(f"Mapped action: {mapped}")

        # Evaluation
        evaluation = meta.get("evaluation")
        if isinstance(evaluation, dict):
            outcome = evaluation.get("outcome", "")
            if outcome:
                reasons.append(f"Evaluation outcome: {outcome}")
        elif evaluation:
            reasons.append(f"Evaluation: {evaluation}")

        # Constraint evaluation
        constraint_eval = meta.get("constraint_evaluation")
        if isinstance(constraint_eval, dict):
            valid = constraint_eval.get("valid", True)
            if not valid:
                reasons.append("Constraint check failed")
        elif constraint_eval:
            reasons.append(f"Constraint: {constraint_eval}")

        # Trace reasons
        trace_reasons = trace.get("reasons", trace.get("decision_reasons", []))
        if isinstance(trace_reasons, list):
            reasons.extend(str(r) for r in trace_reasons)

        # Outcome
        outcome = resolved.get("outcome", "")
        if outcome:
            reasons.append(f"Outcome: {outcome}")

        if not reasons:
            reasons.append("Action resolved via standard pipeline")

        return reasons[:_MAX_REASONS]

    @staticmethod
    def _extract_dialogue_reasons(
        dialogue_response: dict, dialogue_trace: dict
    ) -> list[str]:
        """Extract reasons for an NPC dialogue response."""
        reasons: list[str] = []
        trace = dialogue_trace or {}

        # Decision reasons from trace
        dec_reasons = trace.get("decision_reasons", [])
        if isinstance(dec_reasons, list):
            reasons.extend(str(r) for r in dec_reasons)

        # State drivers
        drivers = trace.get("state_drivers", {})
        if isinstance(drivers, dict):
            for driver_key, driver_val in sorted(drivers.items()):
                reasons.append(f"{driver_key}: {driver_val}")

        # Primary/secondary acts
        primary = trace.get("primary_act", "")
        if primary:
            reasons.append(f"Primary act: {primary}")
        secondary = trace.get("secondary_acts", [])
        if secondary:
            reasons.append(f"Secondary acts: {', '.join(str(s) for s in secondary)}")

        if not reasons:
            # Fall back to response-level data
            act = dialogue_response.get("act", "")
            if act:
                reasons.append(f"Act: {act}")
            else:
                reasons.append("Dialogue reasons unavailable")

        return reasons[:_MAX_REASONS]

    @staticmethod
    def _extract_encounter_reasons(
        encounter_state: dict, encounter_trace: dict
    ) -> list[str]:
        """Extract reasons for the current encounter state."""
        reasons: list[str] = []
        trace = encounter_trace or {}

        # Trace reasons
        trace_reason = trace.get("reasons", trace.get("reason", ""))
        if isinstance(trace_reason, list):
            reasons.extend(str(r) for r in trace_reason)
        elif trace_reason:
            reasons.append(str(trace_reason))

        # Mode
        mode = encounter_state.get("mode") or trace.get("mode")
        if mode:
            reasons.append(f"Mode: {mode}")

        # Status
        status = encounter_state.get("status")
        if status:
            reasons.append(f"Status: {status}")

        # Outcome type
        outcome = trace.get("outcome_type", "")
        if outcome:
            reasons.append(f"Outcome: {outcome}")

        if not reasons:
            reasons.append("Encounter reasons unavailable")

        return reasons[:_MAX_REASONS]

    @staticmethod
    def _extract_world_reasons(
        world_result: dict, world_state: dict | None
    ) -> list[str]:
        """Extract reasons for world-sim tick effects."""
        reasons: list[str] = []

        effects = world_result.get("generated_effects", [])
        if effects:
            # Classify by type
            type_counts: dict[str, int] = {}
            for eff in effects:
                etype = eff.get("effect_type", "unknown")
                type_counts[etype] = type_counts.get(etype, 0) + 1
            for etype, count in sorted(type_counts.items()):
                reasons.append(f"{etype}: {count} effect(s)")

        advanced = world_result.get("advanced", False)
        if advanced:
            reasons.append("World simulation advanced")
        else:
            reasons.append("World simulation did not advance")

        # Guidance/seed context if available
        guidance = world_result.get("guidance", {})
        if isinstance(guidance, dict) and guidance:
            for gk, gv in sorted(guidance.items()):
                reasons.append(f"Guidance {gk}: {gv}")

        if not reasons:
            reasons.append("World sim reasons unavailable")

        return reasons[:_MAX_REASONS]

    @staticmethod
    def _normalize_warning_list(warnings: list[str]) -> list[str]:
        """Deduplicate and bound a warning list."""
        seen: set[str] = set()
        result: list[str] = []
        for w in warnings:
            w_str = str(w)
            if w_str not in seen:
                seen.add(w_str)
                result.append(w_str)
            if len(result) >= _MAX_WARNINGS:
                break
        return result
