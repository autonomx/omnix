"""Coherence and recovery helpers for GameLoop."""
from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

from ..recovery.manager import RecoveryManager
from .event_bus import Event


class GameLoopRecoveryMixin:
    # -------------------------
    # PHASE 6.0 — COHERENCE CORE
    # -------------------------

    def _apply_coherence_updates(self, events: List[Event]) -> Dict[str, Any]:
        """Reduce tick events into canonical coherence state."""
        if self.coherence_core is None:
            return {"events_applied": 0, "mutations": [], "contradictions": []}
        result = self.coherence_core.apply_events(events)
        return result.to_dict()

    def _callable_accepts_kwarg(self, fn: Any, kwarg_name: str) -> bool:
        """Return True if callable explicitly accepts kwarg or **kwargs.

        This avoids using TypeError fallbacks, which can hide real runtime bugs
        thrown inside the target implementation.
        """
        try:
            signature = inspect.signature(fn)
        except (TypeError, ValueError):
            return False

        for param in signature.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return True

        return kwarg_name in signature.parameters

    def _build_director_context(self) -> Dict[str, Any]:
        """Build coherence-aware context for director/renderer consumers."""
        if self.coherence_core is None:
            return {}
        return {
            "scene_summary": self.coherence_core.get_scene_summary(),
            "active_tensions": self.coherence_core.get_active_tensions(),
            "unresolved_threads": self.coherence_core.get_unresolved_threads(),
            "recent_consequences": self.coherence_core.get_recent_consequences(limit=5),
            "last_good_anchor": self.coherence_core.get_last_good_anchor(),
            "contradictions": [c.to_dict() for c in self.coherence_core.get_state().contradictions[-10:]],
        }

    # -------------------------
    # PHASE 6.5 — RECOVERY LAYER
    # -------------------------

    def _init_recovery_manager(self) -> None:
        """Initialize the recovery manager and register for snapshots."""
        self.recovery_manager = RecoveryManager()
        if "recovery_manager" not in self._snapshot_systems:
            self._snapshot_systems.append("recovery_manager")
        # Inject into story director if it supports it
        if hasattr(self.story_director, "set_recovery_manager"):
            self.story_director.set_recovery_manager(self.recovery_manager)

    def _normalize_scene(self, scene: dict | None) -> dict:
        """Normalize a scene dict to a consistent shape.

        Ensures all scenes have canonical keys regardless of source.

        Precedence rules are intentional:
        - root-level keys from the renderer/output scene are authoritative
        - nested narrative keys only backfill missing values
        - `meta` is canonical; `metadata` is kept as a compatibility mirror
        """
        scene = scene or {}
        if not isinstance(scene, dict):
            return {
                "scene": str(scene),
                "options": [],
                "meta": {},
            }

        # If the scene is wrapped in a 'narrative' key (e.g., by renderer),
        # extract the nested payload for backfill only. Root scene keys remain
        # authoritative wherever present.
        narrative_wrapper = scene.get("narrative")
        payload = narrative_wrapper if isinstance(narrative_wrapper, dict) else scene

        # Root scene keys are authoritative; nested narrative only backfills.
        body = (
            scene.get("body")
            or scene.get("scene")
            or scene.get("text")
            or scene.get("description")
            or payload.get("body")
            or payload.get("scene")
            or payload.get("text")
            or payload.get("description")
            or ""
        )

        # Root meta is canonical; nested payload only fills missing keys.
        payload_meta = payload.get("meta", {}) or {}
        payload_metadata = payload.get("metadata", {}) or {}
        scene_meta = scene.get("meta", {}) or {}
        scene_metadata = scene.get("metadata", {}) or {}

        meta = {**payload_meta, **scene_meta}
        metadata = {**payload_metadata, **scene_metadata}

        # Keep metadata synchronized for compatibility, but `meta` remains
        # the canonical place to read recovery flags.
        if "recovered" in meta and "recovered" not in metadata:
            metadata["recovered"] = meta["recovered"]
        if "recovery_reason" in meta and "recovery_reason" not in metadata:
            metadata["recovery_reason"] = meta["recovery_reason"]
        if "recovery_policy" in meta and "recovery_policy" not in metadata:
            metadata["recovery_policy"] = meta["recovery_policy"]

        # Extract options
        options = scene.get("options", []) or payload.get("options", []) or []

        normalized = {
            "scene": body,
            "body": body,
            "options": options,
            "meta": meta,
            "metadata": metadata,
        }

        # Preserve other keys from both payload and scene
        for key in ("title", "summary", "status", "prompt", "scene_data"):
            if key in payload and key not in normalized:
                normalized[key] = payload[key]
            elif key in scene and key not in normalized:
                normalized[key] = scene[key]

        # Keep narrative key if present
        if "narrative" in scene:
            normalized["narrative"] = scene["narrative"]

        return normalized

    def _finalize_scene_output(self, scene: dict, coherence_context: dict | None = None) -> dict:
        """Normalize and finalize a scene for output.

        Single final step applied to all scene outputs regardless of source.
        """
        scene = self._normalize_scene(scene)
        if coherence_context:
            scene.setdefault("meta", {})
            scene["meta"].setdefault("coherence_available", True)
        return scene

    def _is_strong_scene(self, scene: dict) -> bool:
        """Determine if a scene is strong enough to become a last-good anchor.

        Recovered or degraded scenes are NOT considered strong.
        """
        if not isinstance(scene, dict):
            return False
        meta = scene.get("meta", {})
        # Check both meta and metadata keys for backwards compatibility
        if meta.get("recovered") or meta.get("degraded"):
            return False
        metadata = scene.get("metadata", {})
        if metadata.get("recovered") or metadata.get("degraded"):
            return False
        return bool(scene.get("scene") or scene.get("body"))

    def _handle_parser_stage(self, player_input: str) -> tuple:
        """Parse player input with recovery on failure.

        Returns:
            (intent_dict, recovery_scene_or_None)
        """
        coherence_context = self._build_director_context()
        try:
            intent = self.intent_parser.parse(player_input)
        except Exception as exc:
            result = self.recovery_manager.handle_parser_failure(
                player_input=player_input,
                error=exc,
                coherence_summary=coherence_context,
                tick=self._tick_count,
            )
            return {}, result.scene

        # Check for ambiguity signal in parser result
        if isinstance(intent, dict) and intent.get("ambiguous"):
            result = self.recovery_manager.handle_ambiguity(
                player_input=player_input,
                parser_result=intent,
                coherence_summary=coherence_context,
                tick=self._tick_count,
            )
            return intent, result.scene

        return intent, None

    def _handle_director_stage(
        self,
        events: List[Event],
        intent: Dict[str, Any],
        coherence_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run the director stage with recovery on failure."""
        try:
            if self._callable_accepts_kwarg(self.story_director.process, "coherence_context"):
                narrative = self.story_director.process(
                    events, intent, self.event_bus, coherence_context=coherence_context
                )
            else:
                narrative = self.story_director.process(events, intent, self.event_bus)
        except Exception as exc:
            result = self.recovery_manager.handle_director_failure(
                player_input=intent.get("text", ""),
                error=exc,
                coherence_summary=coherence_context,
                tick=self._tick_count,
            )
            return result.scene

        # Guard against empty / malformed director output
        if not narrative or (isinstance(narrative, dict) and not narrative):
            result = self.recovery_manager.handle_director_failure(
                player_input=intent.get("text", ""),
                error="Director returned empty output",
                coherence_summary=coherence_context,
                tick=self._tick_count,
            )
            return result.scene

        return narrative

    def _handle_renderer_stage(
        self,
        narrative: Dict[str, Any],
        coherence_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run the renderer stage with recovery on failure."""
        try:
            if self._callable_accepts_kwarg(self.scene_renderer.render, "coherence_context"):
                scene = self.scene_renderer.render(narrative, coherence_context=coherence_context)
            else:
                scene = self.scene_renderer.render(narrative)
        except Exception as exc:
            result = self.recovery_manager.handle_renderer_failure(
                player_input="",
                error=exc,
                coherence_summary=coherence_context,
                partial_narrative=narrative if isinstance(narrative, dict) else None,
                tick=self._tick_count,
            )
            return result.scene
        return scene

    def _handle_high_severity_contradictions(
        self,
        coherence_result: Dict[str, Any],
        coherence_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """If high-severity contradictions exist, produce a recovery scene.

        Only triggers recovery for high/critical severity contradictions.
        Info and warning contradictions remain visible in state but are
        not player-facing by default.
        """
        contradictions = coherence_result.get("contradictions", [])
        if not contradictions:
            return None
        if not self.recovery_manager._has_high_severity_contradiction(contradictions):
            return None
        result = self.recovery_manager.handle_contradiction(
            contradictions=contradictions,
            coherence_summary=coherence_context,
            tick=self._tick_count,
        )
        return self._finalize_scene_output(result.scene, coherence_context)

    def _maybe_record_last_good_anchor(
        self,
        scene: Dict[str, Any],
        coherence_context: Dict[str, Any],
    ) -> None:
        """After a successful render, update the last-good anchor.

        Only strong (non-recovered, non-degraded) scenes qualify as anchors.
        """
        if not self._is_strong_scene(scene):
            return
        anchor = coherence_context.get("last_good_anchor")
        if not anchor:
            scene_summary = coherence_context.get("scene_summary")
            if (
                isinstance(scene_summary, dict)
                and (
                    scene_summary.get("location")
                    or scene_summary.get("summary")
                    or scene_summary.get("present_actors")
                )
            ):
                anchor = scene_summary
        if anchor:
            self.recovery_manager.record_last_good_anchor(anchor)
