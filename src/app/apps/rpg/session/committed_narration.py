"""A committed turn's narration: written, checked and inserted, its delivery opened (roadmap §4.1 steps 8-10).

``narrate_committed_turn`` runs the six narration steps in order, each in its own pipeline span (the operations view
reads the span names). ``narrate_turn_after_commit`` narrates a turn whose commit has already answered the request:
it reads the campaign as the commit left it first. A step that refuses raises ``NarrationRefused``, which carries the
status and the detail the play screen reads; the edge turns it into its response.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.apps.rpg.foundation.performance_trace import rpg_pipeline_span
from app.apps.rpg.foundation.safe_values import safe_dict


class NarrationRefused(RuntimeError):
    """A narration step refused the turn: ``status_code`` and ``detail`` are what the client is told."""

    def __init__(self, status_code: int, detail: dict[str, Any]) -> None:
        super().__init__(str(detail.get("message") or detail.get("error") or status_code))
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class NarratedTurn:
    """A turn narrated after its commit, and the campaign its commit left."""

    result: dict[str, Any]
    session: dict[str, Any] | None


def narrate_committed_turn(result: dict[str, Any], *, session_id: str, command: str,
                           delivery_mode: Any) -> dict[str, Any]:
    """The committed turn's result with its narration: replay hydrated, presented, delivery opened, consumer bundle
    attached, production checks passed and the shadow report attached."""
    with rpg_pipeline_span("turn.narrative_replay_hydration") as span:
        from app.apps.rpg.narration.narrative_replay import (
            CanonicalNarrativeReplayError,
            hydrate_canonical_narrative_replay,
        )

        try:
            result = hydrate_canonical_narrative_replay(result, campaign_id=session_id)
        except CanonicalNarrativeReplayError as exc:
            span["hydrated"] = False
            span["error"] = str(exc)
            raise NarrationRefused(409, {"ok": False, "error": "canonical_narrative_replay_mismatch",
                                         "session_id": session_id, "message": str(exc)}) from exc
        replay = safe_dict(result.get("canonical_narrative_replay"))
        span["idempotent_replay"] = result.get("idempotent_replay") is True
        span["hydrated"] = replay.get("hydrated") is True
        span["status"] = replay.get("status")
        span["response_id"] = replay.get("response_id")

    with rpg_pipeline_span("turn.narrative_present") as span:
        from app.apps.rpg.session.turn_presenter import TurnPresentationInvariantError, present_authoritative_turn

        try:
            result = present_authoritative_turn(result, session_id=session_id, player_input=command)
        except TurnPresentationInvariantError as exc:
            span["published"] = False
            span["error"] = str(exc)
            raise NarrationRefused(500, {"error": "rpg_turn_presentation_invariant_failed",
                                         "message": str(exc)}) from exc
        canonical = safe_dict(result.get("canonical_narrative_response"))
        span["published"] = bool(canonical)
        span["response_id"] = canonical.get("response_id")
        span["block_count"] = len(canonical.get("blocks") or [])
        span["source"] = result.get("canonical_narrative_source")
        span["request_count"] = result.get("turn_presentation_request_count")

    with rpg_pipeline_span("turn.narrative_delivery_prepare") as span:
        from app.apps.rpg.narration.narrative_delivery import prepare_canonical_result_delivery

        result = prepare_canonical_result_delivery(result, delivery_mode)
        delivery_state = safe_dict(result.get("narrative_delivery_state"))
        span["mode"] = delivery_mode.value
        span["status"] = delivery_state.get("status")
        span["response_id"] = delivery_state.get("response_id")
        span["semantic_hash"] = delivery_state.get("semantic_hash")
        span["next_index"] = delivery_state.get("next_index")

    with rpg_pipeline_span("turn.narrative_consumer_projection") as span:
        from app.apps.rpg.narration.narrative_engine.consumer_publish import attach_canonical_consumer_bundle

        result = attach_canonical_consumer_bundle(result)
        bundle = safe_dict(result.get("narrative_projections"))
        publisher = safe_dict(result.get("narrative_publisher_telemetry"))
        span["attached"] = bool(bundle)
        span["response_id"] = bundle.get("response_id")
        span["content_hash"] = bundle.get("content_hash")
        span["session_patched"] = result.get("narrative_session_projection_patched") is True
        span["publisher"] = result.get("narrative_publisher")
        span["alternate_publish_count"] = publisher.get("alternate_publish_count")
        span["zero_alternate_publishers"] = publisher.get("zero_alternate_publishers")

    with rpg_pipeline_span("turn.narrative_production_certification") as span:
        from app.apps.rpg.narration.narrative_engine.production_path import (
            NarrativeProductionPathError,
            enforce_production_narrative_result,
        )

        try:
            result = enforce_production_narrative_result(result)
        except NarrativeProductionPathError as exc:
            span["passed"] = False
            span["error"] = str(exc)
            raise NarrationRefused(500, {"error": "rpg_narrative_production_certification_failed",
                                         "message": str(exc)}) from exc
        certification = safe_dict(result.get("narrative_production_certification"))
        span["passed"] = certification.get("passed") is True
        span["response_id"] = certification.get("response_id")
        span["content_hash"] = certification.get("content_hash")
        span["legacy_ownership_retired"] = result.get("legacy_presentation_ownership_retired") is True

    with rpg_pipeline_span("turn.narrative_shadow") as span:
        from app.apps.rpg.narration.narrative_engine.shadow import attach_shadow_report

        result = attach_shadow_report(result, session_id=session_id, player_input=command)
        shadow = safe_dict(result.get("narrative_engine_shadow"))
        span["selected"] = shadow.get("selected") is True
        span["ok"] = shadow.get("ok") is True
        span["latency_ms"] = shadow.get("latency_ms")
        span["beat_count"] = len(shadow.get("beat_purposes") or [])

    return result


def narrate_turn_after_commit(result: dict[str, Any], *, session_id: str, command: str) -> NarratedTurn:
    """Narrate a turn whose commit already answered the request, on the campaign as the commit left it.

    The caller holds the scopes: the campaign is never saved here (roadmap §4.1 step 10), so a session save the
    narration's grounding asks for must be staged (``rpg_session_save_policy(defer=True)``).
    """
    from app.apps.rpg.narration.narrative_engine import DeliveryMode
    from app.apps.rpg.narration.narrative_engine.consumer_publish import patch_session_canonical_projection
    from app.apps.rpg.session.narrative_engine_bridge import canonicalize_resolved_turn_result
    from app.apps.rpg.session.service import load_session

    committed = dict(result)
    committed["session"] = load_session(session_id) or result.get("session")
    written = canonicalize_resolved_turn_result(committed, session_id=session_id, player_input=command)
    # The committed document keeps no narration (readers take it from the response table); the copy in hand carries
    # its projection, which the production checks compare.
    patch_session_canonical_projection(written)
    narrated = narrate_committed_turn(written, session_id=session_id, command=command,
                                      delivery_mode=DeliveryMode.BLOCKING)
    return NarratedTurn(result=narrated, session=committed.get("session"))


__all__ = ["NarratedTurn", "NarrationRefused", "narrate_committed_turn", "narrate_turn_after_commit"]
