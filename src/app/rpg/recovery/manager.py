"""Phase 6.5 — Recovery Manager.

Central recovery orchestrator.  Routes parser / director / renderer /
contradiction / ambiguity failures into safe fallback scenes while
maintaining serializable, deterministic state.
"""
from __future__ import annotations

import uuid
from typing import Any

from .ambiguity import AmbiguityPolicy
from .fallbacks import FallbackSceneBuilder
from .models import (
    AmbiguityDecision,
    RecoveryRecord,
    RecoveryResult,
    RecoveryState,
)

_MAX_RECENT_RECOVERIES = 50


class RecoveryManager:
    """Orchestrate recovery for all pipeline failure modes."""

    def __init__(
        self,
        ambiguity_policy: AmbiguityPolicy | None = None,
        fallback_builder: FallbackSceneBuilder | None = None,
    ) -> None:
        self.ambiguity_policy = ambiguity_policy or AmbiguityPolicy()
        self.fallback_builder = fallback_builder or FallbackSceneBuilder()
        self._state = RecoveryState()
        self.mode: str = "live"

    # ------------------------------------------------------------------
    # Mode / anchor bookkeeping
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def record_last_good_anchor(self, anchor: dict) -> None:
        """Store the latest successfully coherent scene anchor."""
        self._state.last_good_scene_anchor = anchor

    # ------------------------------------------------------------------
    # Pipeline failure handlers
    # ------------------------------------------------------------------

    def handle_parser_failure(
        self,
        player_input: str,
        error: Exception | str,
        coherence_summary: dict,
        tick: int | None = None,
    ) -> RecoveryResult:
        reason = "parser_failure"
        anchor = self._state.last_good_scene_anchor
        if anchor:
            scene = self.fallback_builder.build_from_last_good_anchor(
                anchor, coherence_summary
            )
            used_anchor = True
        else:
            scene = self.fallback_builder.build_from_coherence_summary(
                coherence_summary
            )
            used_anchor = False
        record = self._make_record(
            reason=reason,
            summary=f"Parser failed on input: {player_input!r}",
            policy="fallback_scene",
            tick=tick,
            scene_anchor_id=self._last_anchor_id(),
            metadata={"error": str(error)},
        )
        result = RecoveryResult(
            reason=reason,
            policy="fallback_scene",
            scene=scene,
            record=record,
            used_anchor=used_anchor,
            used_coherence_summary=not used_anchor,
        )
        self.record_recovery(result)
        return result

    def handle_director_failure(
        self,
        player_input: str,
        error: Exception | str,
        coherence_summary: dict,
        tick: int | None = None,
    ) -> RecoveryResult:
        reason = "director_failure"
        safe_reason = "The narrative could not advance."
        anchor = self._state.last_good_scene_anchor
        if anchor:
            scene = self.fallback_builder.build_from_last_good_anchor(
                anchor, coherence_summary
            )
            used_anchor = True
        else:
            scene = self.fallback_builder.build_director_failure_scene(
                coherence_summary, reason=safe_reason
            )
            used_anchor = False
        record = self._make_record(
            reason=reason,
            summary=f"Director failed: {safe_reason}",
            policy="fallback_scene",
            tick=tick,
            scene_anchor_id=self._last_anchor_id(),
            metadata={"error": str(error)},
        )
        result = RecoveryResult(
            reason=reason,
            policy="fallback_scene",
            scene=scene,
            record=record,
            used_anchor=used_anchor,
            used_coherence_summary=not used_anchor,
        )
        self.record_recovery(result)
        return result

    def handle_renderer_failure(
        self,
        player_input: str,
        error: Exception | str,
        coherence_summary: dict,
        partial_narrative: dict | None = None,
        tick: int | None = None,
    ) -> RecoveryResult:
        reason = "renderer_failure"
        anchor = self._state.last_good_scene_anchor
        if anchor:
            scene = self.fallback_builder.build_from_last_good_anchor(
                anchor, coherence_summary
            )
            used_anchor = True
        else:
            scene = self.fallback_builder.build_renderer_failure_scene(
                coherence_summary, partial_narrative=partial_narrative
            )
            used_anchor = False
        record = self._make_record(
            reason=reason,
            summary="Renderer failed to produce scene.",
            policy="fallback_scene",
            tick=tick,
            scene_anchor_id=self._last_anchor_id(),
            metadata={"error": str(error)},
        )
        result = RecoveryResult(
            reason=reason,
            policy="fallback_scene",
            scene=scene,
            record=record,
            used_anchor=used_anchor,
            used_coherence_summary=not used_anchor,
        )
        self.record_recovery(result)
        return result

    def handle_contradiction(
        self,
        contradictions: list[dict],
        coherence_summary: dict,
        tick: int | None = None,
    ) -> RecoveryResult:
        reason = "contradiction"
        scene = self.fallback_builder.build_contradiction_recovery_scene(
            contradictions, coherence_summary
        )
        record = self._make_record(
            reason=reason,
            summary=f"Contradiction recovery ({len(contradictions)} items).",
            policy="contradiction_recovery",
            tick=tick,
            scene_anchor_id=self._last_anchor_id(),
            metadata={"contradiction_count": len(contradictions)},
        )
        result = RecoveryResult(
            reason=reason,
            policy="contradiction_recovery",
            scene=scene,
            record=record,
            used_anchor=False,
            used_coherence_summary=True,
        )
        self.record_recovery(result)
        return result

    def handle_ambiguity(
        self,
        player_input: str,
        parser_result: dict | None,
        coherence_summary: dict,
        tick: int | None = None,
    ) -> RecoveryResult:
        decision = self.ambiguity_policy.decide(
            parser_result=parser_result,
            player_input=player_input,
            coherence_summary=coherence_summary,
        )
        if decision == AmbiguityDecision.AUTO_RESOLVE:
            scene = self.fallback_builder.build_from_coherence_summary(
                coherence_summary
            )
            policy = "auto_resolve"
        elif decision == AmbiguityDecision.REQUEST_CLARIFICATION:
            scene = self.fallback_builder.build_clarification_scene(
                player_input, coherence_summary
            )
            policy = "request_clarification"
        else:
            scene = self.fallback_builder.build_from_coherence_summary(
                coherence_summary
            )
            policy = "narrate_uncertainty"

        record = self._make_record(
            reason="ambiguity",
            summary=f"Ambiguity resolved via {policy}.",
            policy=policy,
            tick=tick,
            scene_anchor_id=self._last_anchor_id(),
            metadata={"decision": decision.value, "input": player_input},
        )
        result = RecoveryResult(
            reason="ambiguity",
            policy=policy,
            scene=scene,
            record=record,
            used_anchor=False,
            used_coherence_summary=True,
        )
        self.record_recovery(result)
        return result

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def build_safe_scene(self, coherence_summary: dict, reason: str) -> dict:
        """Build a generic safe scene for any unclassified failure."""
        anchor = self._state.last_good_scene_anchor
        if anchor:
            return self.fallback_builder.build_from_last_good_anchor(
                anchor, coherence_summary
            )
        return self.fallback_builder.build_from_coherence_summary(coherence_summary)

    def record_recovery(self, result: RecoveryResult) -> None:
        """Update internal recovery state from a result."""
        if result.record is not None:
            self._state.recent_recoveries.append(result.record)
            # Cap recent recoveries
            if len(self._state.recent_recoveries) > _MAX_RECENT_RECOVERIES:
                self._state.recent_recoveries = self._state.recent_recoveries[
                    -_MAX_RECENT_RECOVERIES:
                ]
            self._state.last_recovery_reason = result.reason
            self._state.last_recovery_tick = result.record.tick
            self._increment_scene_recovery_count(result.record.scene_anchor_id)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def serialize_state(self) -> dict:
        return {
            "mode": self.mode,
            "state": self._state.to_dict(),
        }

    def deserialize_state(self, data: dict) -> None:
        self.mode = data.get("mode", "live")
        self._state = RecoveryState.from_dict(data.get("state", {}))

    # SnapshotManager extension hooks
    def serialize(self) -> dict:
        return self.serialize_state()

    def deserialize(self, data: dict) -> None:
        self.deserialize_state(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_record(
        self,
        reason: str,
        summary: str,
        policy: str,
        tick: int | None = None,
        scene_anchor_id: str | None = None,
        metadata: dict | None = None,
    ) -> RecoveryRecord:
        return RecoveryRecord(
            recovery_id=uuid.uuid4().hex[:12],
            reason=reason,
            tick=tick,
            scene_anchor_id=scene_anchor_id,
            summary=summary,
            selected_policy=policy,
            metadata=metadata or {},
        )

    def _increment_scene_recovery_count(self, scene_anchor_id: str | None) -> None:
        if scene_anchor_id is None:
            return
        self._state.recovery_count_by_scene[scene_anchor_id] = (
            self._state.recovery_count_by_scene.get(scene_anchor_id, 0) + 1
        )

    def _last_anchor_id(self) -> str | None:
        anchor = self._state.last_good_scene_anchor
        if anchor and isinstance(anchor, dict):
            return anchor.get("anchor_id")
        return None

    def _has_high_severity_contradiction(
        self, contradictions: list[dict]
    ) -> bool:
        return any(
            c.get("severity") in ("high", "critical") for c in contradictions
        )
